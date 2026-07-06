import pytest

from app.application.use_cases.auth.register_user import RegisterUserUseCase
from app.core.security import verify_password
from app.domain.exceptions import EmailAlreadyExistsError
from tests.unit.application.use_cases.auth.fakes import FakeUserRepository


async def test_register_persists_user_with_hashed_password() -> None:
    repo = FakeUserRepository()
    use_case = RegisterUserUseCase(repo)

    user = await use_case.execute("amina@example.com", "hunter2", "Amina")

    assert user.email == "amina@example.com"
    assert user.full_name == "Amina"
    assert user.hashed_password != "hunter2"
    assert verify_password("hunter2", user.hashed_password)
    assert repo.users[user.id] is user


async def test_register_rejects_duplicate_email_and_does_not_overwrite() -> None:
    repo = FakeUserRepository()
    use_case = RegisterUserUseCase(repo)
    original = await use_case.execute("amina@example.com", "hunter2")

    with pytest.raises(EmailAlreadyExistsError):
        await use_case.execute("amina@example.com", "different-password")

    assert repo.users[original.id].hashed_password == original.hashed_password
