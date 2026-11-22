-- Smart Roster Management System - database schema (Supabase / PostgreSQL)
-- Run in the Supabase SQL editor, or via: psql "$DATABASE_URL" -f schema.sql
-- Design goals: every rule is DATA (no hard-coded brands/processes/calendars),
-- operating calendars are separate from employee schedules, and
-- mandatory constraints are separate from preferences.

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------- enums
do $$ begin
  create type calendar_type as enum (
    'all_365',            -- every day incl. Sundays & public holidays
    'daily_ex_holidays',  -- every day except public holidays
    'sun_holiday_off',    -- closed on Sundays and public holidays
    'custom'              -- uses operating_days[] (+ holiday flag)
  );
exception when duplicate_object then null; end $$;

do $$ begin
  create type day_status as enum (
    'working', 'weekly_off', 'holiday_off', 'leave', 'comp_off'
  );
exception when duplicate_object then null; end $$;

do $$ begin
  create type leave_type as enum ('planned_leave', 'sick_leave', 'comp_off');
exception when duplicate_object then null; end $$;

do $$ begin
  create type approval_status as enum ('pending', 'approved', 'rejected');
exception when duplicate_object then null; end $$;

do $$ begin
  create type roster_status as enum ('draft', 'published', 'archived');
exception when duplicate_object then null; end $$;

do $$ begin
  create type severity as enum ('error', 'warning', 'info');
exception when duplicate_object then null; end $$;

-- ---------------------------------------------------------------- core entities
create table if not exists pods (
  id           uuid primary key default gen_random_uuid(),
  name         text not null unique,
  lead_id      uuid,                      -- FK added after employees exists
  created_at   timestamptz not null default now()
);

create table if not exists employees (
  id                 uuid primary key default gen_random_uuid(),
  code               text unique,           -- e.g. EMP-001
  full_name          text not null,
  email              text unique,
  pod_id             uuid references pods(id) on delete set null,
  is_pod_lead        boolean not null default false,
  is_active          boolean not null default true,
  -- scheduling parameters (per employee, all configurable)
  weekly_offs_per_week   smallint not null default 1 check (weekly_offs_per_week between 0 and 3),
  max_consecutive_days   smallint not null default 6 check (max_consecutive_days between 1 and 14),
  -- PREFERENCES (soft): ISO weekday 1=Mon..7=Sun
  preferred_off_days     smallint[] not null default '{}',
  created_at         timestamptz not null default now()
);

do $$ begin
  alter table pods
    add constraint pods_lead_fk foreign key (lead_id)
    references employees(id) on delete set null
    deferrable initially deferred;
exception when duplicate_object then null; end $$;

create table if not exists brands (
  id          uuid primary key default gen_random_uuid(),
  name        text not null unique,
  is_active   boolean not null default true,
  notes       text,
  created_at  timestamptz not null default now()
);

create table if not exists processes (
  id          uuid primary key default gen_random_uuid(),
  code        text not null unique,        -- CS, ACC, RET, NDR ...
  name        text not null,
  created_at  timestamptz not null default now()
);

-- A "brand process" is the unit that needs coverage: e.g. (BrandX, CS).
create table if not exists brand_processes (
  id              uuid primary key default gen_random_uuid(),
  brand_id        uuid not null references brands(id) on delete cascade,
  process_id      uuid not null references processes(id) on delete restrict,
  calendar        calendar_type not null default 'daily_ex_holidays',
  operating_days  smallint[] not null default '{1,2,3,4,5,6,7}',  -- used when calendar='custom'
  min_staff       smallint not null default 1 check (min_staff >= 0),  -- default daily minimum
  is_active       boolean not null default true,
  effective_from  date,
  effective_to    date,
  unique (brand_id, process_id)
);

-- Overrides to min_staff by weekday or by specific date (e.g. Sale days need 2).
create table if not exists coverage_rules (
  id                 uuid primary key default gen_random_uuid(),
  brand_process_id   uuid not null references brand_processes(id) on delete cascade,
  day_of_week        smallint check (day_of_week between 1 and 7),
  on_date            date,
  min_staff          smallint not null check (min_staff >= 0),
  reason             text,
  check (num_nonnulls(day_of_week, on_date) = 1)
);

-- Who covers what. One employee can have many rows (multi-brand / multi-process).
create table if not exists assignments (
  id                 uuid primary key default gen_random_uuid(),
  employee_id        uuid not null references employees(id) on delete cascade,
  brand_process_id   uuid not null references brand_processes(id) on delete cascade,
  allocation_pct     smallint not null default 100 check (allocation_pct between 1 and 100),
  is_primary         boolean not null default true,
  effective_from     date,
  effective_to       date,
  unique (employee_id, brand_process_id)
);

-- ---------------------------------------------------------------- calendar & availability
create table if not exists holidays (
  id          uuid primary key default gen_random_uuid(),
  on_date     date not null unique,
  name        text not null
);

create table if not exists leaves (
  id           uuid primary key default gen_random_uuid(),
  employee_id  uuid not null references employees(id) on delete cascade,
  start_date   date not null,
  end_date     date not null,
  type         leave_type not null default 'planned_leave',
  status       approval_status not null default 'approved',
  reason       text,
  created_at   timestamptz not null default now(),
  check (end_date >= start_date)
);
create index if not exists leaves_emp_dates on leaves (employee_id, start_date, end_date);

-- Optional shifts, to detect incompatible/overlapping shifts across brands.
create table if not exists shifts (
  id          uuid primary key default gen_random_uuid(),
  name        text not null unique,
  start_time  time not null,
  end_time    time not null
);

-- ---------------------------------------------------------------- rosters
-- Multiple versions per month enables draft vs published and "compare plans".
create table if not exists rosters (
  id            uuid primary key default gen_random_uuid(),
  month_start   date not null check (extract(day from month_start) = 1),
  name          text not null default 'Draft',
  status        roster_status not null default 'draft',
  parent_id     uuid references rosters(id) on delete set null,  -- derived-from (regeneration)
  params        jsonb not null default '{}',   -- solver options, weights, seed
  created_at    timestamptz not null default now(),
  published_at  timestamptz
);
create index if not exists rosters_month on rosters (month_start, status);

create table if not exists roster_entries (
  id           uuid primary key default gen_random_uuid(),
  roster_id    uuid not null references rosters(id) on delete cascade,
  employee_id  uuid not null references employees(id) on delete cascade,
  on_date      date not null,
  status       day_status not null,
  shift_id     uuid references shifts(id) on delete set null,
  is_manual    boolean not null default false,  -- edited by a human
  is_locked    boolean not null default false,  -- solver must not touch
  unique (roster_id, employee_id, on_date)
);
create index if not exists entries_roster_date on roster_entries (roster_id, on_date);

-- Validation output, persisted so the manager can track/resolve issues.
create table if not exists conflicts (
  id                 uuid primary key default gen_random_uuid(),
  roster_id          uuid not null references rosters(id) on delete cascade,
  severity           severity not null,
  code               text not null,       -- e.g. NO_COVERAGE, UNDER_MIN_STAFF, MAX_CONSECUTIVE
  on_date            date,
  brand_process_id   uuid references brand_processes(id) on delete cascade,
  employee_id        uuid references employees(id) on delete cascade,
  message            text not null,
  suggestions        jsonb not null default '[]',  -- candidate fixes, ranked
  resolved           boolean not null default false,
  created_at         timestamptz not null default now()
);
create index if not exists conflicts_roster on conflicts (roster_id, severity, resolved);

create table if not exists audit_log (
  id          bigint generated always as identity primary key,
  at          timestamptz not null default now(),
  actor       text,
  action      text not null,
  entity      text,
  entity_id   uuid,
  detail      jsonb
);

-- ---------------------------------------------------------------- convenience view
create or replace view v_assignment_detail as
select a.id as assignment_id, e.id as employee_id, e.full_name, p.name as pod,
       b.id as brand_id, b.name as brand, pr.id as process_id, pr.code as process,
       bp.id as brand_process_id, bp.calendar, bp.min_staff, a.allocation_pct
from assignments a
join employees e on e.id = a.employee_id
left join pods p on p.id = e.pod_id
join brand_processes bp on bp.id = a.brand_process_id
join brands b on b.id = bp.brand_id
join processes pr on pr.id = bp.process_id;

-- Backend connects with the service role / direct DB URL; keep RLS on so the
-- public anon key cannot read or write anything by default.
do $$
declare t text;
begin
  for t in select unnest(array[
    'pods','employees','brands','processes','brand_processes','coverage_rules',
    'assignments','holidays','leaves','shifts','rosters','roster_entries',
    'conflicts','audit_log'])
  loop
    execute format('alter table %I enable row level security', t);
  end loop;
end $$;
