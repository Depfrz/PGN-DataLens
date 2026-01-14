from supabase import Client, create_client

from .app_settings import require_supabase_anon, require_supabase_service, settings


def get_supabase_anon() -> Client:
    require_supabase_anon()
    return create_client(settings.supabase_url, settings.supabase_anon_key)


def get_supabase_service() -> Client:
    require_supabase_service()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
