-- Kiwi: chat storage schema.
--
-- Model: a user (Supabase Auth) owns many conversations; a conversation has many messages.
-- Security: Row Level Security on every table; each user can only reach their own rows.
-- The backend talks to the database with the *user's* JWT, so these policies are the
-- authorization layer — there is no service-role key in the application.

-- ---------------------------------------------------------------------------
-- Types
-- ---------------------------------------------------------------------------
create type public.message_role as enum ('user', 'assistant');

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------
create table public.conversations (
    id          uuid        primary key default gen_random_uuid(),
    user_id     uuid        not null default auth.uid()
                            references auth.users (id) on delete cascade,
    title       text        not null default 'Nueva conversación'
                            check (char_length(title) between 1 and 200),
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),

    -- Target of the composite foreign key in `messages` (keeps ownership consistent).
    unique (id, user_id)
);

comment on table public.conversations is 'A chat thread owned by one user.';

create table public.messages (
    id               bigint generated always as identity primary key,
    conversation_id  uuid               not null,
    -- Denormalized owner: makes RLS a cheap equality check instead of a join.
    user_id          uuid               not null default auth.uid(),
    role             public.message_role not null,
    content          text               not null
                                        check (char_length(content) between 1 and 100000),
    -- Model that produced an assistant message (null for user messages).
    model            text,
    created_at       timestamptz        not null default now(),

    -- A message can only belong to a conversation of the same user.
    foreign key (conversation_id, user_id)
        references public.conversations (id, user_id) on delete cascade,
    check ((role = 'assistant') = (model is not null))
);

comment on table public.messages is 'Immutable chat messages; deleted only with their conversation.';

-- ---------------------------------------------------------------------------
-- Indexes (match the app's queries)
-- ---------------------------------------------------------------------------
-- "My conversations, most recent first".
create index conversations_user_id_updated_at_idx
    on public.conversations (user_id, updated_at desc);

-- "Messages of a conversation in order" (id breaks ties within the same instant).
create index messages_conversation_id_created_at_idx
    on public.messages (conversation_id, created_at, id);

-- ---------------------------------------------------------------------------
-- Triggers
-- ---------------------------------------------------------------------------
create function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    new.updated_at := now();
    return new;
end;
$$;

create trigger conversations_set_updated_at
    before update on public.conversations
    for each row execute function public.set_updated_at();

-- A new message moves its conversation to the top of the list.
-- security definer: users may only update `title` themselves; this trigger needs to touch
-- `updated_at`. Safe because the message insert already passed RLS (same owner), and the
-- function only touches the row referenced by that message.
create function public.touch_conversation()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    update public.conversations
       set updated_at = now()
     where id = new.conversation_id;
    return null;
end;
$$;

create trigger messages_touch_conversation
    after insert on public.messages
    for each row execute function public.touch_conversation();

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
alter table public.conversations enable row level security;
alter table public.messages      enable row level security;

-- `(select auth.uid())` is evaluated once per query instead of once per row.
create policy "Users read their conversations"
    on public.conversations for select to authenticated
    using (user_id = (select auth.uid()));

create policy "Users create their conversations"
    on public.conversations for insert to authenticated
    with check (user_id = (select auth.uid()));

create policy "Users rename their conversations"
    on public.conversations for update to authenticated
    using (user_id = (select auth.uid()))
    with check (user_id = (select auth.uid()));

create policy "Users delete their conversations"
    on public.conversations for delete to authenticated
    using (user_id = (select auth.uid()));

create policy "Users read their messages"
    on public.messages for select to authenticated
    using (user_id = (select auth.uid()));

create policy "Users add messages to their conversations"
    on public.messages for insert to authenticated
    with check (user_id = (select auth.uid()));

-- No update/delete policies on messages: history is append-only.

-- ---------------------------------------------------------------------------
-- Privileges: anonymous visitors get nothing; signed-in users only what they need.
-- ---------------------------------------------------------------------------
revoke all on public.conversations from anon, authenticated;
revoke all on public.messages      from anon, authenticated;

grant select, insert, delete           on public.conversations to authenticated;
grant update (title)                   on public.conversations to authenticated;
grant select, insert                   on public.messages      to authenticated;
grant usage on type public.message_role to authenticated;

revoke execute on function public.set_updated_at()     from public, anon, authenticated;
revoke execute on function public.touch_conversation() from public, anon, authenticated;
