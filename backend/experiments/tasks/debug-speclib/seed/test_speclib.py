import hashlib
import random

INT_DOMAIN = list(range(64))
STR_DOMAIN = ['a dg7', 'filo', 'knqtw', 'psvybe', 'u xadgjm', 'zcfiloru7', 'ehk', 'jmps', 'o ruxa', 'twzcfi', 'ybehknq7', 'dgjmpsvy', 'i lo', 'nqtw', 'svybe', 'xadgjm7', 'c filoru', 'hknqtwzc', 'mps', 'ruxa', 'w zcfi7', 'behknq', 'gjmpsvy', 'loruxadg', 'q tw', 'vybe7', 'adgjm', 'filoru', 'k nqtwzc', 'psvybehk', 'uxa7', 'zcfi', 'e hknq', 'jmpsvy', 'oruxadg', 'twzcfilo7', 'y be', 'dgjm', 'iloru', 'nqtwzc']


def _digest(fn, domain):
    return hashlib.sha256(repr([fn(x) for x in domain]).encode()).hexdigest()

def test_mod00():
    from mod00 import affine
    rng = random.Random(1000)
    for _ in range(40):
        x = rng.choice(INT_DOMAIN)
        y = affine(x)
        assert isinstance(y, int) and y >= 0
    assert _digest(affine, INT_DOMAIN) == '20d8736bc1821281a18344cdd01fd5016e364ce4dbd74e6179226408f68743dd'

def test_mod01():
    from mod01 import digit_sum
    rng = random.Random(1001)
    for _ in range(40):
        x = rng.choice(INT_DOMAIN)
        y = digit_sum(x)
        assert isinstance(y, int) and y >= 0
    assert _digest(digit_sum, INT_DOMAIN) == '612674cc4a95922b69222a81299a8a158f0b5498861e989cfb500bd03f2a1793'

def test_mod02():
    from mod02 import caesar
    rng = random.Random(1002)
    for _ in range(40):
        x = rng.choice(STR_DOMAIN)
        y = caesar(x)
        assert isinstance(y, str) and len(y) == len(x)
    assert _digest(caesar, STR_DOMAIN) == 'e6e37a09c3e1b9754c6f920de55a3a3b7a17622beebd623db653a99f75962c6c'

def test_mod03():
    from mod03 import poly
    rng = random.Random(1003)
    for _ in range(40):
        x = rng.choice(INT_DOMAIN)
        y = poly(x)
        assert isinstance(y, int) and y >= 0
    assert _digest(poly, INT_DOMAIN) == '9440b0b07f46fa80eed0032d352e93ddf3b87f473c9889b1097520de8318a528'

def test_mod04():
    from mod04 import bitrev
    rng = random.Random(1004)
    for _ in range(40):
        x = rng.choice(INT_DOMAIN)
        y = bitrev(x)
        assert isinstance(y, int) and y >= 0
    assert _digest(bitrev, INT_DOMAIN) == '7d9d105457e785cdecac817d353da35c8ce89b3d8962edf5bc9a390895d1788e'

def test_mod05():
    from mod05 import rollhash
    rng = random.Random(1005)
    for _ in range(40):
        x = rng.choice(STR_DOMAIN)
        y = rollhash(x)
        assert isinstance(y, int) and y >= 0
    assert _digest(rollhash, STR_DOMAIN) == 'a26d049bc421b4a3b835b5b9df14f7fdb618df8d5948564891b8361227078b0f'

def test_mod06():
    from mod06 import gray
    rng = random.Random(1006)
    for _ in range(40):
        x = rng.choice(INT_DOMAIN)
        y = gray(x)
        assert isinstance(y, int) and y >= 0
    assert _digest(gray, INT_DOMAIN) == 'a2c5a589a4a8a2c49d1aeabffd1d07ae39251ed7af741c6144b63588081d5eca'

def test_mod07():
    from mod07 import checksum
    rng = random.Random(1007)
    for _ in range(40):
        x = rng.choice(INT_DOMAIN)
        y = checksum(x)
        assert isinstance(y, int) and y >= 0
    assert _digest(checksum, INT_DOMAIN) == 'b23be56d885cd44fdee5aa3b7c90833304dc46707070a7ce75707189c454db42'

def test_mod08():
    from mod08 import affine
    rng = random.Random(1008)
    for _ in range(40):
        x = rng.choice(INT_DOMAIN)
        y = affine(x)
        assert isinstance(y, int) and y >= 0
    assert _digest(affine, INT_DOMAIN) == '510c52a3edc1886de37cc8e17c43a5bd7c055963211b53020e8dd8b4aa99b6d2'

def test_mod09():
    from mod09 import digit_sum
    rng = random.Random(1009)
    for _ in range(40):
        x = rng.choice(INT_DOMAIN)
        y = digit_sum(x)
        assert isinstance(y, int) and y >= 0
    assert _digest(digit_sum, INT_DOMAIN) == '5cbb6e460bb51ee02e2002ffe8147b8960462b0e951abec50f3b683eca8afd1b'

def test_mod10():
    from mod10 import caesar
    rng = random.Random(1010)
    for _ in range(40):
        x = rng.choice(STR_DOMAIN)
        y = caesar(x)
        assert isinstance(y, str) and len(y) == len(x)
    assert _digest(caesar, STR_DOMAIN) == '62f07c081da9a7630d2dbccc701162d0194eacf22c3d505e646e15357b13448e'

def test_mod11():
    from mod11 import poly
    rng = random.Random(1011)
    for _ in range(40):
        x = rng.choice(INT_DOMAIN)
        y = poly(x)
        assert isinstance(y, int) and y >= 0
    assert _digest(poly, INT_DOMAIN) == '55b48cf522f711512d1a2c2f53575d27575f4f0a5673a89eecd918f466257db1'

def test_mod12():
    from mod12 import bitrev
    rng = random.Random(1012)
    for _ in range(40):
        x = rng.choice(INT_DOMAIN)
        y = bitrev(x)
        assert isinstance(y, int) and y >= 0
    assert _digest(bitrev, INT_DOMAIN) == '6759cd22ef03c052682fedf44fa2483423661ac2459a643762b164c37a665a56'

def test_mod13():
    from mod13 import rollhash
    rng = random.Random(1013)
    for _ in range(40):
        x = rng.choice(STR_DOMAIN)
        y = rollhash(x)
        assert isinstance(y, int) and y >= 0
    assert _digest(rollhash, STR_DOMAIN) == 'da566ac4f36442a6dda564db1e0c2e9a194329fdda4f096f44c26c0d385b5270'

def test_mod14():
    from mod14 import gray
    rng = random.Random(1014)
    for _ in range(40):
        x = rng.choice(INT_DOMAIN)
        y = gray(x)
        assert isinstance(y, int) and y >= 0
    assert _digest(gray, INT_DOMAIN) == 'a2c5a589a4a8a2c49d1aeabffd1d07ae39251ed7af741c6144b63588081d5eca'

def test_mod15():
    from mod15 import checksum
    rng = random.Random(1015)
    for _ in range(40):
        x = rng.choice(INT_DOMAIN)
        y = checksum(x)
        assert isinstance(y, int) and y >= 0
    assert _digest(checksum, INT_DOMAIN) == '7d81dfb1559a1e606d0415dd24021f9be29c6d019aa7c0032b10bc3fcb782b2d'

def test_mod16():
    from mod16 import affine
    rng = random.Random(1016)
    for _ in range(40):
        x = rng.choice(INT_DOMAIN)
        y = affine(x)
        assert isinstance(y, int) and y >= 0
    assert _digest(affine, INT_DOMAIN) == 'f06253269fbd3676b27a2bde5f50a3e3e795c72c0b8d94ed14783db7724c2aad'

def test_mod17():
    from mod17 import digit_sum
    rng = random.Random(1017)
    for _ in range(40):
        x = rng.choice(INT_DOMAIN)
        y = digit_sum(x)
        assert isinstance(y, int) and y >= 0
    assert _digest(digit_sum, INT_DOMAIN) == '7e8dfcf8f9490ab8a737f30818f67047f175ffcfa01282721dc22dd4857f8326'

def test_mod18():
    from mod18 import caesar
    rng = random.Random(1018)
    for _ in range(40):
        x = rng.choice(STR_DOMAIN)
        y = caesar(x)
        assert isinstance(y, str) and len(y) == len(x)
    assert _digest(caesar, STR_DOMAIN) == '7b20c9111a5a6a0a1a24eb829c1090193ec7613a7a96ec0a3d95735eb0109afa'

def test_mod19():
    from mod19 import poly
    rng = random.Random(1019)
    for _ in range(40):
        x = rng.choice(INT_DOMAIN)
        y = poly(x)
        assert isinstance(y, int) and y >= 0
    assert _digest(poly, INT_DOMAIN) == 'f8cb2f953d6e31935823036d5aa1d38824f935f5933e217b6101b7c94f33ba64'

def test_mod20():
    from mod20 import bitrev
    rng = random.Random(1020)
    for _ in range(40):
        x = rng.choice(INT_DOMAIN)
        y = bitrev(x)
        assert isinstance(y, int) and y >= 0
    assert _digest(bitrev, INT_DOMAIN) == 'c10079412eadef9cc13a51e6ea2fe2aaf79b360b76b936f7e01b65d48c71ded2'

def test_mod21():
    from mod21 import rollhash
    rng = random.Random(1021)
    for _ in range(40):
        x = rng.choice(STR_DOMAIN)
        y = rollhash(x)
        assert isinstance(y, int) and y >= 0
    assert _digest(rollhash, STR_DOMAIN) == '4ab6a35cef17ecf7692903a9477084964fecc3a0e2b5423fe43d000f3b06edf7'

def test_mod22():
    from mod22 import gray
    rng = random.Random(1022)
    for _ in range(40):
        x = rng.choice(INT_DOMAIN)
        y = gray(x)
        assert isinstance(y, int) and y >= 0
    assert _digest(gray, INT_DOMAIN) == 'a2c5a589a4a8a2c49d1aeabffd1d07ae39251ed7af741c6144b63588081d5eca'

def test_mod23():
    from mod23 import checksum
    rng = random.Random(1023)
    for _ in range(40):
        x = rng.choice(INT_DOMAIN)
        y = checksum(x)
        assert isinstance(y, int) and y >= 0
    assert _digest(checksum, INT_DOMAIN) == '95aaf704e8c700eec5b365418967af03215bd64438910f97c6d9b253d433cd9b'
