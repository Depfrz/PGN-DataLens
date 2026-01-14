from backend.db import get_supabase_service


def main() -> None:
    svc = get_supabase_service()
    page = 1
    per_page = 200
    updated = 0
    scanned = 0

    while True:
        users = svc.auth.admin.list_users(page=page, per_page=per_page)
        if not users:
            break
        for u in users:
            scanned += 1
            uid = getattr(u, "id", None)
            email_confirmed_at = getattr(u, "email_confirmed_at", None)
            if not uid:
                continue
            if email_confirmed_at:
                continue
            svc.auth.admin.update_user_by_id(str(uid), {"email_confirm": True})
            updated += 1
        if len(users) < per_page:
            break
        page += 1

    print({"scanned": scanned, "confirmed": updated})


if __name__ == "__main__":
    main()

