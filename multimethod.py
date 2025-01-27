import collections
import functools
import inspect
import types

origin = ''
try:
  from future_builtins import map, zip
except ImportError:
  import typing

  origin = '__extra__' if hasattr(typing.Type, '__extra__') else '__origin__'

__version__ = '1.1'

class TypeMcs(type):

  __slots__ = ()

  def __getitem__(self, item):
    if isinstance(item, type):
      item = (item,)
    assert isinstance(item, tuple)
    return self(item)


class Type(tuple, metaclass=TypeMcs):
  __slots__ = ()


def get_types(func):
  """Return evaluated type hints in order."""
  annotations = dict(typing.get_type_hints(func))
  annotations.pop('return', None)
  params = inspect.signature(func).parameters

  types = []
  for name, param in params.items():
    if param.default is not inspect._empty:
      break
    types.append(annotations.pop(name, object))

  return tuple(types)


class DispatchError(TypeError):
  pass


def issubtype(*args):
  """`issubclass` with support for generics."""
  if isinstance(args[1], Type):
    if not isinstance(args[0], Type):
      return False
    else:
      return issubtype(tuple(args[0]), tuple(args[1]))

  if isinstance(args[0], tuple):
    return all(issubtype(arg, args[1]) for arg in args[0])

  try:
    return issubclass(*args)
  except TypeError:
    if not origin:
      raise

  return issubclass(*(getattr(cls, origin, cls) for cls in args))

def mro(sub, sup):

  if isinstance(sup, Type):
    assert isinstance(sub, Type)
    return mro(sub[0], tuple(sub))

  if isinstance(sub, Type):
    assert sup is object
    assert len(sub) == 1
    return mro(sub[0], sup)

  if isinstance(sup, tuple):
    return sum(tuple(mro(sub, x) for x in sup), ())
  else:
    mros = sub.mro()
    if sup in mros:
      return mros.index(sup),
    else:
      return len(mros) - 1,


class signature(tuple):
  """A tuple of types that supports partial ordering."""

  def __le__(self, other):
    return len(self) == len(other) and all(map(issubtype, other, self))

  def __lt__(self, other):
    return self != other and self <= other

  def __sub__(self, other):
    """Return relative distances, assuming self >= other."""
    mros = []
    for sub, sup in zip(self, other):
      i = min(mro(sub, sup))
      mros.append(i)
    return mros


class multimethod(dict):
  """A callable directed acyclic graph of methods."""

  def __new__(cls, func, strict=False):
    namespace = inspect.currentframe().f_back.f_locals
    self = functools.update_wrapper(dict.__new__(cls), func)
    self.strict, self.pending = bool(strict), set()
    return namespace.get(func.__name__, self)

  def __init__(self, func, strict=False):
    try:
      self[get_types(func)] = func
    except NameError:
      self.pending.add(func)

  def register(self, func):
    """Decorator for registering function."""
    self.__init__(func)
    return self if self.__name__ == func.__name__ else func

  def __get__(self, instance, owner):
    return self if instance is None else types.MethodType(self, instance)

  def parents(self, types):
    """Find immediate parents of potential key."""
    parents = {key for key in self if isinstance(key, signature) and key < types}
    return parents - {ancestor for parent in parents for ancestor in parent.parents}

  def clean(self):
    """Empty the cache."""
    for key in list(self):
      if not isinstance(key, signature):
        dict.__delitem__(self, key)

  def __setitem__(self, types, func):
    self.clean()
    types = signature(types)
    parents = types.parents = self.parents(types)
    for key in self:
      if types < key and (not parents or parents & key.parents):
        key.parents -= parents
        key.parents.add(types)
    dict.__setitem__(self, types, func)

  def __delitem__(self, types):
    self.clean()
    dict.__delitem__(self, types)
    for key in self:
      if types in key.parents:
        key.parents = self.parents(key)

  def __missing__(self, types):
    """Find and cache the next applicable method of given types."""
    self.evaluate()
    if types in self:
      return self[types]
    keys = self.parents(types)

    if len(keys) == 1 if self.strict else keys:
      return self.setdefault(types, self[min(keys, key=signature(types).__sub__)])
    raise DispatchError("{}{}: {} methods found".format(self.__name__, types, len(keys)))

  def __call__(self, *args, **kwargs):
    """Resolve and dispatch to best method."""
    types = tuple(Type[x] if isinstance(x, type) else type(x) for x in args)
    fn = self[types]
    return fn(*args, ** kwargs)

  def evaluate(self):
    """Evaluate any pending forward references.

    It is recommended to call this explicitly when using forward references,
    otherwise cache misses will be forced to evaluate.
    """
    while self.pending:
      func = self.pending.pop()
      self[get_types(func)] = func


class multidispatch(multimethod):
  def register(self, *types):
    """Return a decorator for registering in the style of `functools.singledispatch`."""
    return lambda func: self.__setitem__(types, func) or func


def isa(*types):
  """Partially bound `isinstance`."""
  return lambda arg: isinstance(arg, types)


class overload(collections.OrderedDict):
  """Ordered functions which dispatch based on their annotated predicates."""

  __get__ = multimethod.__get__
  register = multimethod.register

  def __new__(cls, func):
    namespace = inspect.currentframe().f_back.f_locals
    self = functools.update_wrapper(super().__new__(cls), func)
    return namespace.get(func.__name__, self)

  def __init__(self, func):
    self[inspect.signature(func)] = func

  def __call__(self, *args, **kwargs):
    """Dispatch to first matching function."""
    for sig, func in reversed(self.items()):
      arguments = sig.bind(*args, **kwargs).arguments
      if all(predicate(arguments[name]) for name, predicate in func.__annotations__.items()):
        return func(*args, **kwargs)
    raise DispatchError("No matching functions found")


class multimeta(type):
  """Convert all callables in namespace to multimethods"""

  class multidict(dict):
    def __setitem__(self, key, value):
      curr = self.get(key, None)

      if callable(value):
        if callable(curr) and hasattr(curr, 'register'):
          value = curr.register(value)
        else:
          value = multimethod(value)

      dict.__setitem__(self, key, value)

  @classmethod
  def __prepare__(mcs, name, bases):
    return mcs.multidict()
