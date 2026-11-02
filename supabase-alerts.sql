-- Le Brief Invest · Alertes sur téléphone (ntfy)
-- À lancer UNE fois dans Supabase : SQL Editor → New query → coller → Run.
-- À la fin, Supabase affiche une ligne « secret » : copie-la dans GitHub
-- (Settings → Secrets and variables → Actions → New repository secret, nom : ALERT_SECRET).
-- Ne la partage avec personne d'autre.

-- 1) Réglages d'alertes de chaque membre (chacun ne voit et ne modifie que les siens)
create table if not exists public.alert_subs (
  user_id    uuid primary key references auth.users(id) on delete cascade,
  topic      text not null check (topic ~ '^[A-Za-z0-9_-]{16,64}$'),
  keywords   text[] not null default '{}',
  assets     text[] not null default '{}',
  pct        numeric not null default 5 check (pct between 1 and 50),
  news       boolean not null default true,
  enabled    boolean not null default true,
  updated_at timestamptz not null default now()
);
alter table public.alert_subs enable row level security;
drop policy if exists "alertes perso" on public.alert_subs;
create policy "alertes perso" on public.alert_subs for all to authenticated
  using (auth.uid() = user_id) with check (auth.uid() = user_id);
grant select, insert, update, delete on public.alert_subs to authenticated;

-- 2) Mot de passe du robot (table fermée : aucune lecture possible depuis le site)
create table if not exists public.robot_secret (id int primary key default 1 check (id = 1), secret text not null);
alter table public.robot_secret enable row level security;
revoke all on public.robot_secret from anon, authenticated;
insert into public.robot_secret (id, secret)
values (1, replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', ''))
on conflict (id) do nothing;

-- 3) Seul le robot (avec le bon mot de passe) peut lire la liste des alertes actives
create or replace function public.robot_alert_subs(p_secret text)
returns setof public.alert_subs
language sql security definer set search_path = public as $$
  select a.* from public.alert_subs a
  where a.enabled and exists (select 1 from public.robot_secret r where r.secret = p_secret);
$$;
revoke all on function public.robot_alert_subs(text) from public;
grant execute on function public.robot_alert_subs(text) to anon, authenticated;

-- 4) Affiche le mot de passe à copier dans GitHub (secret ALERT_SECRET)
select secret from public.robot_secret;
