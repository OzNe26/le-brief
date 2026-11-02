-- ============================================================
--  Le Brief : base de données (à coller dans Supabase > SQL Editor > Run)
--  Peut être relancé sans risque.
-- ============================================================

-- 1. Profils (pseudo public de chaque membre)
create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  pseudo text not null unique check (char_length(pseudo) between 2 and 24),
  created_at timestamptz not null default now()
);

-- 2. Préférences perso (favoris + liste à surveiller), privées
create table if not exists public.user_prefs (
  user_id uuid primary key references auth.users(id) on delete cascade,
  saved jsonb not null default '[]'::jsonb,
  watch jsonb not null default '[]'::jsonb,
  updated_at timestamptz not null default now()
);

-- 3. Communauté
create table if not exists public.posts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade default auth.uid(),
  text text not null default '' check (char_length(text) <= 1500),
  link text check (link is null or char_length(link) <= 500),
  tag text not null default 'Général' check (char_length(tag) <= 20),
  article jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.comments (
  id uuid primary key default gen_random_uuid(),
  post_id uuid not null references public.posts(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade default auth.uid(),
  text text not null check (char_length(text) between 1 and 800),
  created_at timestamptz not null default now()
);

create table if not exists public.likes (
  post_id uuid not null references public.posts(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade default auth.uid(),
  created_at timestamptz not null default now(),
  primary key (post_id, user_id)
);

create index if not exists posts_created_idx on public.posts (created_at desc);
create index if not exists comments_post_idx on public.comments (post_id);

-- 4. Sécurité : chacun ne peut modifier que ses propres données
alter table public.profiles   enable row level security;
alter table public.user_prefs enable row level security;
alter table public.posts      enable row level security;
alter table public.comments   enable row level security;
alter table public.likes      enable row level security;

drop policy if exists "profils lisibles"        on public.profiles;
drop policy if exists "profil perso insert"     on public.profiles;
drop policy if exists "profil perso update"     on public.profiles;
create policy "profils lisibles"    on public.profiles for select using (true);
create policy "profil perso insert" on public.profiles for insert to authenticated with check (auth.uid() = id);
create policy "profil perso update" on public.profiles for update to authenticated using (auth.uid() = id) with check (auth.uid() = id);

drop policy if exists "prefs perso" on public.user_prefs;
create policy "prefs perso" on public.user_prefs for all to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "posts lisibles"   on public.posts;
drop policy if exists "posts creer"      on public.posts;
drop policy if exists "posts supprimer"  on public.posts;
create policy "posts lisibles"  on public.posts for select using (true);
create policy "posts creer"     on public.posts for insert to authenticated with check (auth.uid() = user_id);
create policy "posts supprimer" on public.posts for delete to authenticated using (auth.uid() = user_id);

drop policy if exists "comments lisibles"  on public.comments;
drop policy if exists "comments creer"     on public.comments;
drop policy if exists "comments supprimer" on public.comments;
create policy "comments lisibles"  on public.comments for select using (true);
create policy "comments creer"     on public.comments for insert to authenticated with check (auth.uid() = user_id);
create policy "comments supprimer" on public.comments for delete to authenticated using (auth.uid() = user_id);

drop policy if exists "likes lisibles"  on public.likes;
drop policy if exists "likes creer"     on public.likes;
drop policy if exists "likes supprimer" on public.likes;
create policy "likes lisibles"  on public.likes for select using (true);
create policy "likes creer"     on public.likes for insert to authenticated with check (auth.uid() = user_id);
create policy "likes supprimer" on public.likes for delete to authenticated using (auth.uid() = user_id);

grant select on public.profiles, public.posts, public.comments, public.likes to anon, authenticated;
grant insert, update on public.profiles to authenticated;
grant select, insert, update, delete on public.user_prefs to authenticated;
grant insert, delete on public.posts, public.comments, public.likes to authenticated;

-- 5. Création automatique du profil à l'inscription (avec le pseudo choisi)
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
declare p text;
begin
  p := coalesce(nullif(trim(new.raw_user_meta_data->>'pseudo'), ''), split_part(new.email, '@', 1));
  p := left(p, 24);
  if char_length(p) < 2 then p := p || '_'; end if;
  if exists (select 1 from public.profiles where lower(pseudo) = lower(p)) then
    p := left(p, 19) || '_' || substr(md5(new.id::text), 1, 4);
  end if;
  insert into public.profiles (id, pseudo) values (new.id, p) on conflict (id) do nothing;
  return new;
end; $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

-- 6. Vérifier si un pseudo est déjà pris (utilisé par le formulaire d'inscription)
create or replace function public.pseudo_dispo(p text)
returns boolean language sql security definer set search_path = public stable as $$
  select not exists (select 1 from public.profiles where lower(pseudo) = lower(trim(p)));
$$;
grant execute on function public.pseudo_dispo(text) to anon, authenticated;

-- Radios favorites et progression des podcasts (ajout du 2 nov. 2026)
alter table public.user_prefs add column if not exists radios jsonb not null default '[]'::jsonb;
alter table public.user_prefs add column if not exists progress jsonb not null default '{}'::jsonb;
