import pytest
from typing import List
from multimethod import isa, multimethod, overload, multimeta, signature, DispatchError, Type


# string join
class tree(list):
    def walk(self):
        for value in self:
            if isinstance(value, type(self)):
                yield from value.walk()
            else:
                yield value


class bracket(tuple):
    def __new__(cls, left, right):
        return tuple.__new__(cls, (left, right))


@multimethod
def join(seq, sep):
    return sep.join(map(str, seq))


@multimethod
def join(seq: object, sep: bracket):
    return sep[0] + join(seq, sep[1] + sep[0]) + sep[1]


@multimethod
def join(seq: tree, sep: object):
    return join(seq.walk(), sep)


def test_join():
    sep = '<>'
    seq = [0, tree([1]), 2]
    assert list(tree(seq).walk()) == list(range(3))
    assert join(seq, sep) == '0<>[1]<>2'
    assert join(tree(seq), sep) == '0<>1<>2'
    assert join(seq, bracket(*sep)) == '<0><[1]><2>'
    assert join(tree(seq), bracket(*sep)) == '<0><1><2>'


# type hints
def test_signature():
    assert signature([List]) <= signature([list])
    assert signature([list]) <= signature([List])
    assert signature([List[int]]) <= signature([list])
    assert signature([list]) <= signature([List[int]])
    assert signature([List[int]]) - signature([list]) == [0]
    assert signature([list]) - signature([List[int]]) == [1]


class cls:
    @multimethod
    def method(x, y: int, z=None) -> tuple:
        return object, int

    @multimethod
    def method(x: 'cls', y: float):
        return type(x), float


def test_annotations():
    obj = cls()
    assert obj.method(0.0) == (cls, float)  # run first to check exact match post-evaluation
    assert obj.method(0) == (object, int)
    assert cls.method(None, 0) == (object, int)
    with pytest.raises(DispatchError):
        cls.method(None, 0.0)


# register out of order
@multimethod
def func(arg: bool):
    return bool


@func.register
def _(arg: object):
    return object


@func.register
def _(arg: int):
    return int


def test_register():
    func.strict = True
    assert func(0.0) is object
    assert func(0) is int
    assert func(False) is bool


def test_overloads():
    @overload
    def func(x):
        return x

    @overload
    def func(x: isa(int, float)):
        return -x

    @func.register
    def _(x: isa(str)):
        return x.upper()

    assert func(None) is None
    assert func(1) == -1
    assert func('hi') == 'HI'
    del func[next(iter(func))]
    with pytest.raises(DispatchError):
        func(None)


# multimeta


def test_meta():
    class meta(metaclass=multimeta):
        def method(self, x: str):
            return 'STR'

        def method(self, x: int):
            return 'INT'

        def normal(self, y):
            return 'OBJECT'

        def rebind(self, x: str):
            return 'INITIAL'

        rebind = 2

        def rebind(self, x):
            return 'REBOUND'

    assert isinstance(meta.method, multimethod)
    assert isinstance(meta.normal, multimethod)
    assert isinstance(meta.rebind, multimethod)

    m = meta()

    assert m.method('') == 'STR'
    assert m.method(12) == 'INT'
    assert m.normal('') == 'OBJECT'
    assert m.rebind('') == 'REBOUND'


A, B, C = (type(n, (), {}) for n in ("A", "B", "C"))

@multimethod
def comb(_: Type[A], __: Type[B]):
    return "AB"

@multimethod
def comb(_: Type[B], __: Type[C]):
    return "BC"


@multimethod
def comb(_: Type[A], __: Type[A, C]):
    return "AAC"


@multimethod
def comb(_: Type[A, B], __: Type[B]):
    return "BB"

@multimethod
def comb(_: Type[A, B], x):
    return "A only"


def test_dispatch_on_type():

    assert comb(A, B) == "AB"
    assert comb(B, C) == "BC"
    assert comb(A, C) == "AAC"
    assert comb(A, A) == "AAC"
    assert comb(B, B) == "BB"
    assert comb(A, int) == "A only"
    with pytest.raises(DispatchError):
        comb(A(), B())


@multimethod
def narg(a, b, c):
    return 3

@multimethod
def narg(a, b):
    return 2


def test_dispatch_on_nargs():
    assert narg(1, 2, 3) == 3
    assert narg(1, 2) == 2
    