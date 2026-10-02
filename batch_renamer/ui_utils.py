"""UI 相关的纯 Python 小工具（不依赖 Kivy，方便单元测试）。

这里只放「与图形库无关、但必须绝对可靠」的规整逻辑。
之所以单独成模块，是因为真机闪退的根因就在这类参数规整上，
而 Kivy 本身在 CI 里装不上，放在这里才能被 pytest 覆盖到。
"""

__all__ = ["normalize_radius"]


def normalize_radius(radius, default=10.0):
    """把各种写法的圆角半径规整成「Kivy 一定接受」的形式。

    背景（真机闪退根因，勿删）：
        Kivy 的 ``RoundedRectangle`` 对 radius 的校验规则是——
        把 radius 当成可迭代对象逐个检查元素：
          * ``tuple``        -> 合法（四角 tuple 写法）
          * ``int`` / ``float`` -> 合法
          * 其它（含 ``list``）-> 直接抛
            ``GraphicException: Invalid radius value, must be list of tuples/numerics``

        所以 ``[dp(18)]`` 这种「单元素 list」被再包一层变成 ``[[18.0]]``
        （嵌套 list）时，Kivy 必炸；而这个异常发生在 ``App.build()``
        期间，会被 CPython 走 ``Py_Exit`` 直接退出进程，
        在真机上表现为「打开即闪退」，且随后还会引发 GPU/HWUI 层的
        次生报错，极易误导排查方向。

    规整规则：
        * ``int`` / ``float``       -> ``[值]``
        * ``[值]`` / ``(值,)``      -> ``[值]``（拆掉一层无意义包裹）
        * ``[[值]]``                -> ``[值]``（拆掉嵌套，修掉本次 bug）
        * ``[(a, b), (c, d), ...]`` -> 原样保留（Kivy 的四角写法）
        * ``[(a, b, c, d)]``        -> 原样保留（单个四角 tuple 也不能拆）
        * ``None`` / 空 / 其它非法  -> ``[default]``

    注意：只拆「外层是单元素 list，且那个元素本身是 list」这一种嵌套，
    或者 ``[(值,)]`` 这种单元素 tuple。像 ``[(a, b, c, d)]`` 这种把四角
    信息放在 tuple 里的写法绝不能拆，否则会丢掉 Kivy 的角语义。

    :param radius: 待规整的半径值
    :param default: 兜底半径（非法输入时使用）
    :return: 非空的 list，元素只可能是 ``int`` / ``float`` / ``tuple``
    """
    fallback = _as_number(default, 10.0)

    if radius is None:
        return [fallback]

    # bool 是 int 的子类，但在半径语义上没有意义，直接当非法处理
    if isinstance(radius, bool):
        return [fallback]

    if isinstance(radius, (int, float)):
        return [float(radius)]

    if not isinstance(radius, (list, tuple)):
        return [fallback]

    values = list(radius)

    # 只拆「无意义的一层包裹」，且绝不能破坏 tuple 的四角语义：
    #   [[18.0]]    -> [18.0]      （本次闪退的元凶）
    #   [[(a, b)]]  -> [(a, b)]    （嵌套 list 拆掉）
    #   [(18.0,)]   -> [18.0]      （单元素 tuple 等于标量）
    #   [(a, b, c, d)] / [(a,b),(c,d)] -> 原样保留，tuple 承担角信息
    if len(values) == 1:
        inner = values[0]
        if isinstance(inner, list):
            values = list(inner)
        elif isinstance(inner, tuple) and len(inner) == 1:
            values = list(inner)

    cleaned = []
    for value in values:
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            cleaned.append(float(value))
        elif isinstance(value, tuple):
            # Kivy 的四角 tuple 写法，原样透传
            cleaned.append(value)
        # 其余（残余 list / str / None ...）一律丢弃，绝不让它冒泡到 Kivy
    return cleaned or [fallback]


def _as_number(value, default):
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default
