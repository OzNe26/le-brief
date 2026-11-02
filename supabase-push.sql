-- Le Brief Invest · Notifications du site (sans appli à télécharger)
-- À lancer UNE fois dans Supabase : SQL Editor → New query → coller → Run.
-- (Nécessite d'avoir déjà lancé supabase-alerts.sql.)

-- 1) Le canal ntfy devient facultatif
alter table public.alert_subs alter column topic drop not null;
alter table public.alert_subs drop constraint if exists alert_subs_topic_check;
alter table public.alert_subs add constraint alert_subs_topic_check
  check (topic is null or topic ~ '^[A-Za-z0-9_-]{16,64}$');

-- 2) Appareils abonnés aux notifications (chacun ne voit que les siens)
create table if not exists public.push_subs (
  endpoint   text primary key check (endpoint like 'https://%' and length(endpoint) < 1000),
  user_id    uuid not null default auth.uid() references auth.users(id) on delete cascade,
  p256dh     text not null check (length(p256dh) < 200),
  auth       text not null check (length(auth) < 100),
  device     text check (device is null or length(device) < 120),
  created_at timestamptz not null default now()
);
alter table public.push_subs enable row level security;
drop policy if exists "appareils perso" on public.push_subs;
create policy "appareils perso" on public.push_subs for all to authenticated
  using (auth.uid() = user_id) with check (auth.uid() = user_id);
grant select, insert, update, delete on public.push_subs to authenticated;

-- 3) Pour le robot (protégé par le mot de passe du robot) : réglages + appareils de chacun
create or replace function public.robot_alert_targets(p_secret text)
returns table (user_id uuid, topic text, keywords text[], assets text[], pct numeric, news boolean, endpoints jsonb)
language sql security definer set search_path = public as $$
  select a.user_id, a.topic, a.keywords, a.assets, a.pct, a.news,
         coalesce((select jsonb_agg(jsonb_build_object('endpoint', p.endpoint, 'p256dh', p.p256dh, 'auth', p.auth))
                   from public.push_subs p where p.user_id = a.user_id), '[]'::jsonb)
  from public.alert_subs a
  where a.enabled and exists (select 1 from public.robot_secret r where r.secret = p_secret);
$$;
revoke all on function public.robot_alert_targets(text) from public;
grant execute on function public.robot_alert_targets(text) to anon, authenticated;

-- 4) Le robot retire les appareils qui n'existent plus (appli désinstallée, notifications coupées)
create or replace function public.robot_remove_push(p_secret text, p_endpoint text)
returns void
language sql security definer set search_path = public as $$
  delete from public.push_subs
  where endpoint = p_endpoint and exists (select 1 from public.robot_secret r where r.secret = p_secret);
$$;
revoke all on function public.robot_remove_push(text, text) from public;
grant execute on function public.robot_remove_push(text, text) to anon, authenticated;
