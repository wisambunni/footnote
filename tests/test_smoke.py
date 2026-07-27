from footnote import main


def test_main_runs(capsys):
    main()
    assert "footnote" in capsys.readouterr().out
