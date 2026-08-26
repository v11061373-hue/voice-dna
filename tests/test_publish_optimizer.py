"""发布优化 tool 契约测试。

run() 返回 {"platform","best_time","tags","hashtags","description"}；
platform 默认 threads，可被 script 里的 platform 覆盖；无输入不抛异常。
"""

from src.tools.publish_optimizer import run


def test_run_returns_dict_with_contract_keys():
    out = run()
    assert isinstance(out, dict)
    for key in ("platform", "best_time", "tags", "hashtags", "description"):
        assert key in out


def test_default_platform_is_threads_and_best_time_nonempty():
    out = run()
    assert out["platform"] == "threads"
    assert out["best_time"]


def test_tags_and_hashtags_are_lists():
    out = run(script={"body": "AI agents for social media"})
    assert isinstance(out["tags"], list)
    assert isinstance(out["hashtags"], list)


def test_no_input_does_not_raise():
    out = run()
    assert out["tags"] == []


def test_script_platform_overrides_default():
    out = run(script={"platform": "tiktok", "body": "x"})
    assert out["platform"] == "tiktok"
