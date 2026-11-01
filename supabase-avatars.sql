-- Le Brief Invest · Photos de profil
-- À lancer UNE fois dans Supabase : SQL Editor → New query → coller → Run.
-- Sans danger si relancé.

-- 1) Colonne pour l'adresse de la photo
alter table public.profiles add column if not exists avatar_url text;
alter table public.profiles drop constraint if exists avatar_url_len;
alter table public.profiles add constraint avatar_url_len check (avatar_url is null or (length(avatar_url) <= 500 and avatar_url like 'https://%'));

-- 2) Espace de stockage public « avatars » (512 Ko max par image, images seulement)
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('avatars', 'avatars', true, 524288, array['image/jpeg','image/png','image/webp'])
on conflict (id) do update set public = true, file_size_limit = 524288,
  allowed_mime_types = array['image/jpeg','image/png','image/webp'];

-- 3) Règles : chacun ne peut ajouter / remplacer / supprimer que les photos de SON dossier
drop policy if exists "avatars : voir son dossier"    on storage.objects;
drop policy if exists "avatars : ajouter dans son dossier" on storage.objects;
drop policy if exists "avatars : modifier son dossier"     on storage.objects;
drop policy if exists "avatars : supprimer son dossier"    on storage.objects;

create policy "avatars : voir son dossier" on storage.objects for select to authenticated
  using (bucket_id = 'avatars' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy "avatars : ajouter dans son dossier" on storage.objects for insert to authenticated
  with check (bucket_id = 'avatars' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy "avatars : modifier son dossier" on storage.objects for update to authenticated
  using (bucket_id = 'avatars' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy "avatars : supprimer son dossier" on storage.objects for delete to authenticated
  using (bucket_id = 'avatars' and (storage.foldername(name))[1] = (select auth.uid())::text);
