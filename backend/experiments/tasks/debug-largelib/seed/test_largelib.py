"""Oracle suite for largelib. DO NOT EDIT - fix the modules until green."""
from largelib.textkit import slugify, truncate, word_count, title_case
from largelib.numkit import clamp, running_max, is_prime, gcd
from largelib.listkit import chunk, dedupe, flatten, windows
from largelib.dictkit import invert, merge_sum, group_by_len, pick
from largelib.seqkit import rle_encode, rotate, pairwise_diff

def test_textkit_slugify():
    assert slugify("  Hi, There! ") == 'hi-there'
    assert slugify("!!a!!") == 'a'

def test_textkit_truncate():
    assert truncate("hello world", 8) == 'hello...'
    assert len(truncate("hello world", 8)) == 8

def test_textkit_word_count():
    assert word_count("a   b  c") == 3
    assert word_count("  x  ") == 1

def test_textkit_title_case():
    assert title_case("the QUICK fox") == 'The Quick Fox'

def test_numkit_clamp():
    assert clamp(5, 0, 10) == 5
    assert clamp(-1, 0, 10) == 0
    assert clamp(99, 0, 10) == 10

def test_numkit_running_max():
    assert running_max([1,3,2,5,4]) == [1, 3, 3, 5, 5]

def test_numkit_is_prime():
    assert is_prime(7) == True
    assert is_prime(9) == False
    assert is_prime(2) == True

def test_numkit_gcd():
    assert gcd(12, 18) == 6
    assert gcd(17, 5) == 1

def test_listkit_chunk():
    assert chunk([1,2,3,4,5], 2) == [[1, 2], [3, 4], [5]]

def test_listkit_dedupe():
    assert dedupe([1,1,2,3,3,1]) == [1, 2, 3]

def test_listkit_flatten():
    assert flatten([[1,2],[3],[4,5]]) == [1, 2, 3, 4, 5]

def test_listkit_windows():
    assert windows([1,2,3,4], 2) == [[1, 2], [2, 3], [3, 4]]

def test_dictkit_invert():
    assert invert({"a": 1, "b": 2}) == {1: 'a', 2: 'b'}

def test_dictkit_merge_sum():
    assert merge_sum({"x": 1, "y": 2}, {"y": 3, "z": 4}) == {'x': 1, 'y': 5, 'z': 4}

def test_dictkit_group_by_len():
    assert group_by_len(["a", "bb", "cc", "d"]) == {1: ['a', 'd'], 2: ['bb', 'cc']}

def test_dictkit_pick():
    assert pick({"a": 1, "b": 2}, ["a", "z"]) == {'a': 1}

def test_seqkit_rle_encode():
    assert rle_encode("aaabb") == [('a', 3), ('b', 2)]

def test_seqkit_rotate():
    assert rotate([1,2,3,4,5], 2) == [3, 4, 5, 1, 2]
    assert rotate([1,2,3], 4) == [2, 3, 1]

def test_seqkit_pairwise_diff():
    assert pairwise_diff([1,4,9,16]) == [3, 5, 7]

