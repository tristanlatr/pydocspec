from typing import List, Optional, Type
import pytest

from . import mod_from_text_param, ModFromTextFunction
from pydocspec import Class, ApiObject, processor

def assert_mro_equals(klass: Optional[ApiObject], expected_mro: List[str]
    ) -> None:
    assert isinstance(klass, Class)
    assert [member.full_name for member in processor.class_attr.MRO().mro(klass)] == expected_mro

@mod_from_text_param
def test_mro(mod_from_text: ModFromTextFunction) -> None:
    mod = mod_from_text("""\
    from mod import External
    class C: pass
    class D(C): pass
    class A1: pass
    class B1(A1): pass
    class C1(A1): pass
    class D1(B1, C1): pass
    class E1(C1, B1): pass
    class F1(D1, E1): pass
    class G1(E1, D1): pass
    class Boat: pass
    class DayBoat(Boat): pass
    class WheelBoat(Boat): pass
    class EngineLess(DayBoat): pass
    class SmallMultihull(DayBoat): pass
    class PedalWheelBoat(EngineLess, WheelBoat): pass
    class SmallCatamaran(SmallMultihull): pass
    class Pedalo(PedalWheelBoat, SmallCatamaran): pass
    class OuterA:
        class Inner:
            pass
    class OuterB(OuterA):
        class Inner(OuterA.Inner):
            pass
    class OuterC(OuterA):
        class Inner(OuterA.Inner):
            pass
    class OuterD(OuterC):
        class Inner(OuterC.Inner, OuterB.Inner):
            pass
    class Duplicates(C, C): pass
    class Extension(External): pass
    class MycustomString(str): pass
    """, 
    modname='mro', 
    )
    assert_mro_equals(mod.get_member("D"), ["mro.D", "mro.C"])
    assert_mro_equals(mod.get_member("D1"), ['mro.D1', 'mro.B1', 'mro.C1', 'mro.A1'])
    assert_mro_equals(mod.get_member("E1"), ['mro.E1', 'mro.C1', 'mro.B1', 'mro.A1'])
    assert_mro_equals(mod.get_member("Extension"), ["mro.Extension"])
    assert_mro_equals(mod.get_member("MycustomString"), ["mro.MycustomString"])
    
    assert_mro_equals(
        mod.get_member("PedalWheelBoat"),
        ["mro.PedalWheelBoat", "mro.EngineLess", "mro.DayBoat", "mro.WheelBoat", "mro.Boat"],
    )

    assert_mro_equals(
        mod.get_member("SmallCatamaran"),
        ["mro.SmallCatamaran", "mro.SmallMultihull", "mro.DayBoat", "mro.Boat"],
    )

    assert_mro_equals(
        mod.get_member("Pedalo"),
        [
            "mro.Pedalo",
            "mro.PedalWheelBoat",
            "mro.EngineLess",
            "mro.SmallCatamaran",
            "mro.SmallMultihull",
            "mro.DayBoat",
            "mro.WheelBoat",
            "mro.Boat"
        ],
    )

    assert_mro_equals(
        mod["OuterD.Inner"],
        ['mro.OuterD.Inner', 
        'mro.OuterC.Inner',
        'mro.OuterB.Inner', 
        'mro.OuterA.Inner']
    )

    with pytest.raises(ValueError, match="Cannot compute c3 linearization"):
        processor.class_attr.MRO().mro(mod["F1"]) # type:ignore[arg-type]
    with pytest.raises(ValueError, match="Cannot compute c3 linearization"):
        processor.class_attr.MRO().mro(mod["G1"]) # type:ignore[arg-type]
    with pytest.raises(ValueError, match="Cannot compute c3 linearization"):
        processor.class_attr.MRO().mro(mod["Duplicates"]) # type:ignore[arg-type]
