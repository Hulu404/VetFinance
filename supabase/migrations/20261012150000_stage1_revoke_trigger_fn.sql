-- create_default_connections is a trigger function; it must not be reachable through /rest/v1/rpc.
revoke all on function public.create_default_connections() from public, anon, authenticated;
