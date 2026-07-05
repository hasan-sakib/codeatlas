from app.main import create_app


def test_create_app_is_idempotent() -> None:
    app_one = create_app()
    app_two = create_app()

    assert app_one is not app_two
    assert {r.path for r in app_one.routes} == {r.path for r in app_two.routes}
