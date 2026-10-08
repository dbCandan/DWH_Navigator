"""Create the super admin or reset its password, activation and role; the operator's only path.

application-foundation/PRDs/001-user-accounts Requirement 18: the command shares its creation path
with the backend start (app.services.super_admin_service). It reads the password only from its
prompt or, with --password-stdin, from one line of standard input; the deployment's start-up
password (DWHNAVIGATOR_BOOTSTRAP_SUPER_ADMIN_PASSWORD) is never used. The account name comes from
--username, otherwise from DWHNAVIGATOR_BOOTSTRAP_SUPER_ADMIN_USERNAME. The password set here
works once: the account chooses its own password at its first login.
"""

import argparse
import asyncio
import getpass
import sys

import app.db.base  # noqa: F401  # populate mapper metadata before any write
from app.core.config import get_settings
from app.db.session import async_session_factory, engine
from app.services.super_admin_service import (
    SuperAdminRejected,
    SuperAdminResult,
    ensure_super_admin,
)


def _password_from_operator(use_stdin: bool) -> str:
    if use_stdin:
        password = sys.stdin.readline().rstrip("\n")
        if not password:
            raise SystemExit("Parola girilmedi.")
        return password
    first = getpass.getpass("Süper yönetici parolası: ")
    second = getpass.getpass("Parola (tekrar): ")
    if first != second:
        raise SystemExit("Parolalar aynı değil.")
    return first


async def _run(args: argparse.Namespace) -> SuperAdminResult:
    settings = get_settings()
    password = _password_from_operator(args.password_stdin)
    try:
        async with async_session_factory() as session:
            return await ensure_super_admin(
                session,
                username=args.username or settings.bootstrap_super_admin_username,
                password=password,
                email=(
                    args.email if args.email is not None else settings.bootstrap_super_admin_email
                ),
            )
    finally:
        # The pooled connections belong to this command's event loop; close them with it.
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create the application super admin or reset its password"
    )
    parser.add_argument("--username")
    parser.add_argument("--email")
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="read one password line from standard input instead of prompting",
    )
    try:
        result = asyncio.run(_run(parser.parse_args()))
    except SuperAdminRejected as rejected:
        reasons = {
            "invalid_username": (
                "Kullanıcı adı 3-64 karakter olmalı ve yalnız a-z, 0-9, nokta, alt çizgi ve "
                "kısa çizgi içermeli."
            ),
            "password_policy": (
                "Parola kurala uymuyor: en az 15 karakter olmalı; yaygın bir parola, kullanıcı "
                "adı ya da uygulamanın adı olamaz ve şimdiki parolayla aynı olamaz."
            ),
            "identity_conflict": "Bu e-posta adresi başka bir hesapta kullanılıyor.",
        }
        raise SystemExit(reasons[rejected.reason]) from None
    action = "açıldı" if result.created else "sıfırlandı"
    print(
        f"Süper yönetici {action}: kullanıcı={result.user_public_id} "
        f"kiracı={result.tenant_public_id}. İlk girişte yeni parola belirlenecek."
    )


if __name__ == "__main__":
    main()
