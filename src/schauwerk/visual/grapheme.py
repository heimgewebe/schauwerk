"""Stdlib-only Unicode extended-grapheme segmenter for the native runtime.

The embedded range snapshot contains only Unicode properties required by the
UAX #29 extended-grapheme rules. Production execution intentionally has no
third-party dependency; the snapshot was generated and is conformance-checked
during development.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterator

_OTHER = 0
_CR = 1
_LF = 2
_CONTROL = 3
_EXTEND = 4
_ZWJ = 5
_RI = 6
_PREPEND = 7
_SPACINGMARK = 8
_L = 9
_V = 10
_T = 11
_LV = 12
_LVT = 13

_INCB_NONE = 0
_INCB_CONSONANT = 1
_INCB_LINKER = 2
_INCB_EXTEND = 3

MAX_GRAPHEME_CLUSTER_CODEPOINTS = 256

_CONTROL_SPEC = (
    "0-9,B-C,E-1F,7F-9F,AD,61C,180E,200B,200E-200F,2028-202E,2060-206F,FEFF,FFF0-FFFB,13430-1343F,"
    "1BCA0-1BCA3,1D173-1D17A,E0000-E001F,E0080-E00FF,E01F0-E0FFF,"
)

_EXTEND_SPEC = (
    "300-36F,483-489,591-5BD,5BF,5C1-5C2,5C4-5C5,5C7,610-61A,64B-65F,670,6D6-6DC,6DF-6E4,6E7-6E8,"
    "6EA-6ED,711,730-74A,7A6-7B0,7EB-7F3,7FD,816-819,81B-823,825-827,829-82D,859-85B,897-89F,8CA-8E1,"
    "8E3-902,93A,93C,941-948,94D,951-957,962-963,981,9BC,9BE,9C1-9C4,9CD,9D7,9E2-9E3,9FE,A01-A02,A3C,"
    "A41-A42,A47-A48,A4B-A4D,A51,A70-A71,A75,A81-A82,ABC,AC1-AC5,AC7-AC8,ACD,AE2-AE3,AFA-AFF,B01,B3C,"
    "B3E-B3F,B41-B44,B4D,B55-B57,B62-B63,B82,BBE,BC0,BCD,BD7,C00,C04,C3C,C3E-C40,C46-C48,C4A-C4D,"
    "C55-C56,C62-C63,C81,CBC,CBF-CC0,CC2,CC6-CC8,CCA-CCD,CD5-CD6,CE2-CE3,D00-D01,D3B-D3C,D3E,D41-D44,"
    "D4D,D57,D62-D63,D81,DCA,DCF,DD2-DD4,DD6,DDF,E31,E34-E3A,E47-E4E,EB1,EB4-EBC,EC8-ECE,F18-F19,F35,"
    "F37,F39,F71-F7E,F80-F84,F86-F87,F8D-F97,F99-FBC,FC6,102D-1030,1032-1037,1039-103A,103D-103E,"
    "1058-1059,105E-1060,1071-1074,1082,1085-1086,108D,109D,135D-135F,1712-1715,1732-1734,1752-1753,"
    "1772-1773,17B4-17B5,17B7-17BD,17C6,17C9-17D3,17DD,180B-180D,180F,1885-1886,18A9,1920-1922,"
    "1927-1928,1932,1939-193B,1A17-1A18,1A1B,1A56,1A58-1A5E,1A60,1A62,1A65-1A6C,1A73-1A7C,1A7F,"
    "1AB0-1ADD,1AE0-1AEB,1B00-1B03,1B34-1B3D,1B42-1B44,1B6B-1B73,1B80-1B81,1BA2-1BA5,1BA8-1BAD,1BE6,"
    "1BE8-1BE9,1BED,1BEF-1BF3,1C2C-1C33,1C36-1C37,1CD0-1CD2,1CD4-1CE0,1CE2-1CE8,1CED,1CF4,1CF8-1CF9,"
    "1DC0-1DFF,200C,20D0-20F0,2CEF-2CF1,2D7F,2DE0-2DFF,302A-302F,3099-309A,A66F-A672,A674-A67D,"
    "A69E-A69F,A6F0-A6F1,A802,A806,A80B,A825-A826,A82C,A8C4-A8C5,A8E0-A8F1,A8FF,A926-A92D,A947-A951,"
    "A953,A980-A982,A9B3,A9B6-A9B9,A9BC-A9BD,A9C0,A9E5,AA29-AA2E,AA31-AA32,AA35-AA36,AA43,AA4C,AA7C,"
    "AAB0,AAB2-AAB4,AAB7-AAB8,AABE-AABF,AAC1,AAEC-AAED,AAF6,ABE5,ABE8,ABED,FB1E,FE00-FE0F,FE20-FE2F,"
    "FF9E-FF9F,101FD,102E0,10376-1037A,10A01-10A03,10A05-10A06,10A0C-10A0F,10A38-10A3A,10A3F,"
    "10AE5-10AE6,10D24-10D27,10D69-10D6D,10EAB-10EAC,10EFA-10EFF,10F46-10F50,10F82-10F85,11001,"
    "11038-11046,11070,11073-11074,1107F-11081,110B3-110B6,110B9-110BA,110C2,11100-11102,11127-1112B,"
    "1112D-11134,11173,11180-11181,111B6-111BE,111C0,111C9-111CC,111CF,1122F-11231,11234-11237,1123E,"
    "11241,112DF,112E3-112EA,11300-11301,1133B-1133C,1133E,11340,1134D,11357,11366-1136C,11370-11374,"
    "113B8,113BB-113C0,113C2,113C5,113C7-113C9,113CE-113D0,113D2,113E1-113E2,11438-1143F,11442-11444,"
    "11446,1145E,114B0,114B3-114B8,114BA,114BD,114BF-114C0,114C2-114C3,115AF,115B2-115B5,115BC-115BD,"
    "115BF-115C0,115DC-115DD,11633-1163A,1163D,1163F-11640,116AB,116AD,116B0-116B7,1171D,1171F,"
    "11722-11725,11727-1172B,1182F-11837,11839-1183A,11930,1193B-1193E,11943,119D4-119D7,119DA-119DB,"
    "119E0,11A01-11A0A,11A33-11A38,11A3B-11A3E,11A47,11A51-11A56,11A59-11A5B,11A8A-11A96,11A98-11A99,"
    "11B60,11B62-11B64,11B66,11C30-11C36,11C38-11C3D,11C3F,11C92-11CA7,11CAA-11CB0,11CB2-11CB3,"
    "11CB5-11CB6,11D31-11D36,11D3A,11D3C-11D3D,11D3F-11D45,11D47,11D90-11D91,11D95,11D97,11EF3-11EF4,"
    "11F00-11F01,11F36-11F3A,11F40-11F42,11F5A,13440,13447-13455,1611E-16129,1612D-1612F,16AF0-16AF4,"
    "16B30-16B36,16F4F,16F8F-16F92,16FE4,16FF0-16FF1,1BC9D-1BC9E,1CF00-1CF2D,1CF30-1CF46,1D165-1D169,"
    "1D16D-1D172,1D17B-1D182,1D185-1D18B,1D1AA-1D1AD,1D242-1D244,1DA00-1DA36,1DA3B-1DA6C,1DA75,1DA84,"
    "1DA9B-1DA9F,1DAA1-1DAAF,1E000-1E006,1E008-1E018,1E01B-1E021,1E023-1E024,1E026-1E02A,1E08F,"
    "1E130-1E136,1E2AE,1E2EC-1E2EF,1E4EC-1E4EF,1E5EE-1E5EF,1E6E3,1E6E6,1E6EE-1E6EF,1E6F5,1E8D0-1E8D6,"
    "1E944-1E94A,1F3FB-1F3FF,E0020-E007F,E0100-E01EF,"
)

_PREPEND_SPEC = (
    "600-605,6DD,70F,890-891,8E2,D4E,110BD,110CD,111C2-111C3,113D1,1193F,11941,11A84-11A89,11D46,"
    "11F02,"
)

_SPACINGMARK_SPEC = (
    "903,93B,93E-940,949-94C,94E-94F,982-983,9BF-9C0,9C7-9C8,9CB-9CC,A03,A3E-A40,A83,ABE-AC0,AC9,"
    "ACB-ACC,B02-B03,B40,B47-B48,B4B-B4C,BBF,BC1-BC2,BC6-BC8,BCA-BCC,C01-C03,C41-C44,C82-C83,CBE,CC1,"
    "CC3-CC4,CF3,D02-D03,D3F-D40,D46-D48,D4A-D4C,D82-D83,DD0-DD1,DD8-DDE,DF2-DF3,E33,EB3,F3E-F3F,F7F,"
    "1031,103B-103C,1056-1057,1084,17B6,17BE-17C5,17C7-17C8,1923-1926,1929-192B,1930-1931,1933-1938,"
    "1A19-1A1A,1A55,1A57,1A6D-1A72,1B04,1B3E-1B41,1B82,1BA1,1BA6-1BA7,1BE7,1BEA-1BEC,1BEE,1C24-1C2B,"
    "1C34-1C35,1CE1,1CF7,A823-A824,A827,A880-A881,A8B4-A8C3,A952,A983,A9B4-A9B5,A9BA-A9BB,A9BE-A9BF,"
    "AA2F-AA30,AA33-AA34,AA4D,AAEB,AAEE-AAEF,AAF5,ABE3-ABE4,ABE6-ABE7,ABE9-ABEA,ABEC,11000,11002,"
    "11082,110B0-110B2,110B7-110B8,1112C,11145-11146,11182,111B3-111B5,111BF,111CE,1122C-1122E,"
    "11232-11233,112E0-112E2,11302-11303,1133F,11341-11344,11347-11348,1134B-1134C,11362-11363,"
    "113B9-113BA,113CA,113CC-113CD,11435-11437,11440-11441,11445,114B1-114B2,114B9,114BB-114BC,114BE,"
    "114C1,115B0-115B1,115B8-115BB,115BE,11630-11632,1163B-1163C,1163E,116AC,116AE-116AF,1171E,11726,"
    "1182C-1182E,11838,11931-11935,11937-11938,11940,11942,119D1-119D3,119DC-119DF,119E4,11A39,"
    "11A57-11A58,11A97,11B61,11B65,11B67,11C2F,11C3E,11CA9,11CB1,11CB4,11D8A-11D8E,11D93-11D94,11D96,"
    "11EF5-11EF6,11F03,11F34-11F35,11F3E-11F3F,1612A-1612C,16F51-16F87,"
)

_EXTENDED_PICTOGRAPHIC_SPEC = (
    "A9,AE,203C,2049,2122,2139,2194-2199,21A9-21AA,231A-231B,2328,23CF,23E9-23F3,23F8-23FA,24C2,"
    "25AA-25AB,25B6,25C0,25FB-25FE,2600-2604,260E,2611,2614-2615,2618,261D,2620,2622-2623,2626,262A,"
    "262E-262F,2638-263A,2640,2642,2648-2653,265F-2660,2663,2665-2666,2668,267B,267E-267F,2692-2697,"
    "2699,269B-269C,26A0-26A1,26A7,26AA-26AB,26B0-26B1,26BD-26BE,26C4-26C5,26C8,26CE-26CF,26D1,"
    "26D3-26D4,26E9-26EA,26F0-26F5,26F7-26FA,26FD,2702,2705,2708-270D,270F,2712,2714,2716,271D,2721,"
    "2728,2733-2734,2744,2747,274C,274E,2753-2755,2757,2763-2764,2795-2797,27A1,27B0,27BF,2934-2935,"
    "2B05-2B07,2B1B-2B1C,2B50,2B55,3030,303D,3297,3299,1F004,1F02C-1F02F,1F094-1F09F,1F0AF-1F0B0,"
    "1F0C0,1F0CF-1F0D0,1F0F6-1F0FF,1F170-1F171,1F17E-1F17F,1F18E,1F191-1F19A,1F1AE-1F1E5,1F201-1F20F,"
    "1F21A,1F22F,1F232-1F23A,1F23C-1F23F,1F249-1F25F,1F266-1F321,1F324-1F393,1F396-1F397,1F399-1F39B,"
    "1F39E-1F3F0,1F3F3-1F3F5,1F3F7-1F3FA,1F400-1F4FD,1F4FF-1F53D,1F549-1F54E,1F550-1F567,1F56F-1F570,"
    "1F573-1F57A,1F587,1F58A-1F58D,1F590,1F595-1F596,1F5A4-1F5A5,1F5A8,1F5B1-1F5B2,1F5BC,1F5C2-1F5C4,"
    "1F5D1-1F5D3,1F5DC-1F5DE,1F5E1,1F5E3,1F5E8,1F5EF,1F5F3,1F5FA-1F64F,1F680-1F6C5,1F6CB-1F6D2,"
    "1F6D5-1F6E5,1F6E9,1F6EB-1F6F0,1F6F3-1F6FF,1F7DA-1F7FF,1F80C-1F80F,1F848-1F84F,1F85A-1F85F,"
    "1F888-1F88F,1F8AE-1F8AF,1F8BC-1F8BF,1F8C2-1F8CF,1F8D9-1F8FF,1F90C-1F93A,1F93C-1F945,1F947-1F9FF,"
    "1FA58-1FA5F,1FA6E-1FAFF,1FC00-1FFFD,"
)

_INCB_CONSONANT_SPEC = (
    "915-939,958-95F,978-97F,995-9A8,9AA-9B0,9B2,9B6-9B9,9DC-9DD,9DF,9F0-9F1,A95-AA8,AAA-AB0,AB2-AB3,"
    "AB5-AB9,AF9,B15-B28,B2A-B30,B32-B33,B35-B39,B5C-B5D,B5F,B71,C15-C28,C2A-C39,C58-C5A,D15-D3A,"
    "1000-102A,103F,1050-1055,105A-105D,1061,1065-1066,106E-1070,1075-1081,108E,1780-17B3,1A20-1A54,"
    "1B0B-1B0C,1B13-1B33,1B45-1B4C,1B83-1BA0,1BAE-1BAF,1BBB-1BBD,A989-A98B,A98F-A9B2,A9E0-A9E4,"
    "A9E7-A9EF,A9FA-A9FE,AA60-AA6F,AA71-AA73,AA7A,AA7E-AA7F,AAE0-AAEA,ABC0-ABDA,10A00,10A10-10A13,"
    "10A15-10A17,10A19-10A35,11103-11126,11144,11147,11380-11389,1138B,1138E,11390-113B5,11900-11906,"
    "11909,1190C-11913,11915-11916,11918-1192F,11A00,11A0B-11A32,11A50,11A5C-11A83,11F04-11F10,"
    "11F12-11F33,"
)

_INCB_LINKER_SPEC = (
    "94D,9CD,ACD,B4D,C4D,D4D,1039,17D2,1A60,1B44,1BAB,A9C0,AAF6,10A3F,11133,113D0,1193E,11A47,11A99,"
    "11F42,"
)

_INCB_EXTEND_SPEC = (
    "300-36F,483-489,591-5BD,5BF,5C1-5C2,5C4-5C5,5C7,610-61A,64B-65F,670,6D6-6DC,6DF-6E4,6E7-6E8,"
    "6EA-6ED,711,730-74A,7A6-7B0,7EB-7F3,7FD,816-819,81B-823,825-827,829-82D,859-85B,897-89F,8CA-8E1,"
    "8E3-902,93A,93C,941-948,951-957,962-963,981,9BC,9BE,9C1-9C4,9D7,9E2-9E3,9FE,A01-A02,A3C,A41-A42,"
    "A47-A48,A4B-A4D,A51,A70-A71,A75,A81-A82,ABC,AC1-AC5,AC7-AC8,AE2-AE3,AFA-AFF,B01,B3C,B3E-B3F,"
    "B41-B44,B55-B57,B62-B63,B82,BBE,BC0,BCD,BD7,C00,C04,C3C,C3E-C40,C46-C48,C4A-C4C,C55-C56,C62-C63,"
    "C81,CBC,CBF-CC0,CC2,CC6-CC8,CCA-CCD,CD5-CD6,CE2-CE3,D00-D01,D3B-D3C,D3E,D41-D44,D57,D62-D63,D81,"
    "DCA,DCF,DD2-DD4,DD6,DDF,E31,E34-E3A,E47-E4E,EB1,EB4-EBC,EC8-ECE,F18-F19,F35,F37,F39,F71-F7E,"
    "F80-F84,F86-F87,F8D-F97,F99-FBC,FC6,102D-1030,1032-1037,103A,103D-103E,1058-1059,105E-1060,"
    "1071-1074,1082,1085-1086,108D,109D,135D-135F,1712-1715,1732-1734,1752-1753,1772-1773,17B4-17B5,"
    "17B7-17BD,17C6,17C9-17D1,17D3,17DD,180B-180D,180F,1885-1886,18A9,1920-1922,1927-1928,1932,"
    "1939-193B,1A17-1A18,1A1B,1A56,1A58-1A5E,1A62,1A65-1A6C,1A73-1A7C,1A7F,1AB0-1ADD,1AE0-1AEB,"
    "1B00-1B03,1B34-1B3D,1B42-1B43,1B6B-1B73,1B80-1B81,1BA2-1BA5,1BA8-1BAA,1BAC-1BAD,1BE6,1BE8-1BE9,"
    "1BED,1BEF-1BF3,1C2C-1C33,1C36-1C37,1CD0-1CD2,1CD4-1CE0,1CE2-1CE8,1CED,1CF4,1CF8-1CF9,1DC0-1DFF,"
    "200D,20D0-20F0,2CEF-2CF1,2D7F,2DE0-2DFF,302A-302F,3099-309A,A66F-A672,A674-A67D,A69E-A69F,"
    "A6F0-A6F1,A802,A806,A80B,A825-A826,A82C,A8C4-A8C5,A8E0-A8F1,A8FF,A926-A92D,A947-A951,A953,"
    "A980-A982,A9B3,A9B6-A9B9,A9BC-A9BD,A9E5,AA29-AA2E,AA31-AA32,AA35-AA36,AA43,AA4C,AA7C,AAB0,"
    "AAB2-AAB4,AAB7-AAB8,AABE-AABF,AAC1,AAEC-AAED,ABE5,ABE8,ABED,FB1E,FE00-FE0F,FE20-FE2F,FF9E-FF9F,"
    "101FD,102E0,10376-1037A,10A01-10A03,10A05-10A06,10A0C-10A0F,10A38-10A3A,10AE5-10AE6,10D24-10D27,"
    "10D69-10D6D,10EAB-10EAC,10EFA-10EFF,10F46-10F50,10F82-10F85,11001,11038-11046,11070,11073-11074,"
    "1107F-11081,110B3-110B6,110B9-110BA,110C2,11100-11102,11127-1112B,1112D-11132,11134,11173,"
    "11180-11181,111B6-111BE,111C0,111C9-111CC,111CF,1122F-11231,11234-11237,1123E,11241,112DF,"
    "112E3-112EA,11300-11301,1133B-1133C,1133E,11340,1134D,11357,11366-1136C,11370-11374,113B8,"
    "113BB-113C0,113C2,113C5,113C7-113C9,113CE-113CF,113D2,113E1-113E2,11438-1143F,11442-11444,11446,"
    "1145E,114B0,114B3-114B8,114BA,114BD,114BF-114C0,114C2-114C3,115AF,115B2-115B5,115BC-115BD,"
    "115BF-115C0,115DC-115DD,11633-1163A,1163D,1163F-11640,116AB,116AD,116B0-116B7,1171D,1171F,"
    "11722-11725,11727-1172B,1182F-11837,11839-1183A,11930,1193B-1193D,11943,119D4-119D7,119DA-119DB,"
    "119E0,11A01-11A0A,11A33-11A38,11A3B-11A3E,11A51-11A56,11A59-11A5B,11A8A-11A96,11A98,11B60,"
    "11B62-11B64,11B66,11C30-11C36,11C38-11C3D,11C3F,11C92-11CA7,11CAA-11CB0,11CB2-11CB3,11CB5-11CB6,"
    "11D31-11D36,11D3A,11D3C-11D3D,11D3F-11D45,11D47,11D90-11D91,11D95,11D97,11EF3-11EF4,11F00-11F01,"
    "11F36-11F3A,11F40-11F41,11F5A,13440,13447-13455,1611E-16129,1612D-1612F,16AF0-16AF4,16B30-16B36,"
    "16F4F,16F8F-16F92,16FE4,16FF0-16FF1,1BC9D-1BC9E,1CF00-1CF2D,1CF30-1CF46,1D165-1D169,1D16D-1D172,"
    "1D17B-1D182,1D185-1D18B,1D1AA-1D1AD,1D242-1D244,1DA00-1DA36,1DA3B-1DA6C,1DA75,1DA84,1DA9B-1DA9F,"
    "1DAA1-1DAAF,1E000-1E006,1E008-1E018,1E01B-1E021,1E023-1E024,1E026-1E02A,1E08F,1E130-1E136,1E2AE,"
    "1E2EC-1E2EF,1E4EC-1E4EF,1E5EE-1E5EF,1E6E3,1E6E6,1E6EE-1E6EF,1E6F5,1E8D0-1E8D6,1E944-1E94A,"
    "1F3FB-1F3FF,E0020-E007F,E0100-E01EF,"
)



def _decode_ranges(spec: str) -> tuple[tuple[int, int], ...]:
    values: list[tuple[int, int]] = []
    for token in spec.split(","):
        if not token:
            continue
        if "-" in token:
            first, last = token.split("-", 1)
        else:
            first = last = token
        values.append((int(first, 16), int(last, 16)))
    return tuple(values)


_CONTROL_RANGES = _decode_ranges(_CONTROL_SPEC)
_EXTEND_RANGES = _decode_ranges(_EXTEND_SPEC)
_PREPEND_RANGES = _decode_ranges(_PREPEND_SPEC)
_SPACINGMARK_RANGES = _decode_ranges(_SPACINGMARK_SPEC)
_EXTENDED_PICTOGRAPHIC_RANGES = _decode_ranges(_EXTENDED_PICTOGRAPHIC_SPEC)
_INCB_CONSONANT_RANGES = _decode_ranges(_INCB_CONSONANT_SPEC)
_INCB_LINKER_RANGES = _decode_ranges(_INCB_LINKER_SPEC)
_INCB_EXTEND_RANGES = _decode_ranges(_INCB_EXTEND_SPEC)

_CONTROL_STARTS = tuple(first for first, _ in _CONTROL_RANGES)
_EXTEND_STARTS = tuple(first for first, _ in _EXTEND_RANGES)
_PREPEND_STARTS = tuple(first for first, _ in _PREPEND_RANGES)
_SPACINGMARK_STARTS = tuple(first for first, _ in _SPACINGMARK_RANGES)
_EXTENDED_PICTOGRAPHIC_STARTS = tuple(
    first for first, _ in _EXTENDED_PICTOGRAPHIC_RANGES
)
_INCB_CONSONANT_STARTS = tuple(first for first, _ in _INCB_CONSONANT_RANGES)
_INCB_LINKER_STARTS = tuple(first for first, _ in _INCB_LINKER_RANGES)
_INCB_EXTEND_STARTS = tuple(first for first, _ in _INCB_EXTEND_RANGES)


def _in_ranges(
    codepoint: int,
    ranges: tuple[tuple[int, int], ...],
    starts: tuple[int, ...],
) -> bool:
    index = bisect_right(starts, codepoint) - 1
    return index >= 0 and codepoint <= ranges[index][1]


def _grapheme_break_property(character: str) -> int:
    codepoint = ord(character)
    if codepoint == 0x000D:
        return _CR
    if codepoint == 0x000A:
        return _LF
    if codepoint == 0x200D:
        return _ZWJ
    if 0x1F1E6 <= codepoint <= 0x1F1FF:
        return _RI
    if 0x1100 <= codepoint <= 0x115F or 0xA960 <= codepoint <= 0xA97C:
        return _L
    if 0x1160 <= codepoint <= 0x11A7 or 0xD7B0 <= codepoint <= 0xD7C6:
        return _V
    if 0x11A8 <= codepoint <= 0x11FF or 0xD7CB <= codepoint <= 0xD7FB:
        return _T
    if 0xAC00 <= codepoint <= 0xD7A3:
        return _LV if (codepoint - 0xAC00) % 28 == 0 else _LVT
    if _in_ranges(codepoint, _CONTROL_RANGES, _CONTROL_STARTS):
        return _CONTROL
    if _in_ranges(codepoint, _EXTEND_RANGES, _EXTEND_STARTS):
        return _EXTEND
    if _in_ranges(codepoint, _PREPEND_RANGES, _PREPEND_STARTS):
        return _PREPEND
    if _in_ranges(codepoint, _SPACINGMARK_RANGES, _SPACINGMARK_STARTS):
        return _SPACINGMARK
    return _OTHER


def is_extended_pictographic(character: str) -> bool:
    return _in_ranges(
        ord(character),
        _EXTENDED_PICTOGRAPHIC_RANGES,
        _EXTENDED_PICTOGRAPHIC_STARTS,
    )


def _indic_conjunct_break(character: str) -> int:
    codepoint = ord(character)
    if _in_ranges(codepoint, _INCB_CONSONANT_RANGES, _INCB_CONSONANT_STARTS):
        return _INCB_CONSONANT
    if _in_ranges(codepoint, _INCB_LINKER_RANGES, _INCB_LINKER_STARTS):
        return _INCB_LINKER
    if _in_ranges(codepoint, _INCB_EXTEND_RANGES, _INCB_EXTEND_STARTS):
        return _INCB_EXTEND
    return _INCB_NONE


def _should_break(cluster: list[str], character: str) -> bool:
    previous = cluster[-1]
    previous_property = _grapheme_break_property(previous)
    current_property = _grapheme_break_property(character)

    if previous_property == _CR and current_property == _LF:
        return False
    if previous_property in {_CONTROL, _CR, _LF}:
        return True
    if current_property in {_CONTROL, _CR, _LF}:
        return True
    if previous_property == _L and current_property in {_L, _V, _LV, _LVT}:
        return False
    if previous_property in {_LV, _V} and current_property in {_V, _T}:
        return False
    if previous_property in {_LVT, _T} and current_property == _T:
        return False
    if current_property in {_EXTEND, _ZWJ}:
        return False
    if current_property == _SPACINGMARK:
        return False
    if previous_property == _PREPEND:
        return False

    if _indic_conjunct_break(character) == _INCB_CONSONANT:
        index = len(cluster) - 1
        saw_linker = False
        while index >= 0:
            property_value = _indic_conjunct_break(cluster[index])
            if property_value == _INCB_LINKER:
                saw_linker = True
            elif property_value != _INCB_EXTEND:
                break
            index -= 1
        if (
            saw_linker
            and index >= 0
            and _indic_conjunct_break(cluster[index]) == _INCB_CONSONANT
        ):
            return False

    if is_extended_pictographic(character) and previous == "\u200d":
        index = len(cluster) - 2
        while index >= 0 and _grapheme_break_property(cluster[index]) == _EXTEND:
            index -= 1
        if index >= 0 and is_extended_pictographic(cluster[index]):
            return False

    if previous_property == _RI and current_property == _RI:
        regional_indicator_count = 0
        index = len(cluster) - 1
        while index >= 0 and _grapheme_break_property(cluster[index]) == _RI:
            regional_indicator_count += 1
            index -= 1
        if regional_indicator_count % 2 == 1:
            return False

    return True


def bounded_grapheme_prefix(
    value: str,
    *,
    max_cluster_codepoints: int = MAX_GRAPHEME_CLUSTER_CODEPOINTS,
    max_clusters: int | None = None,
    max_codepoints: int | None = None,
) -> tuple[str, bool]:
    """Return a cluster-boundary prefix under explicit grapheme scan limits.

    The scan never retains more than max_cluster_codepoints code points for one
    candidate cluster. With max_clusters omitted, behavior remains exact unless
    a pathological cluster exceeds that cap. With max_clusters set, scanning
    also stops after that many complete clusters. max_codepoints additionally
    bounds total source work while returning only complete grapheme clusters.
    Any active limit reports truncation when source content remains.
    """

    if max_cluster_codepoints < 1:
        raise ValueError("max_cluster_codepoints must be positive")
    if max_clusters is not None and max_clusters < 1:
        raise ValueError("max_clusters must be positive")
    if max_codepoints is not None and max_codepoints < 1:
        raise ValueError("max_codepoints must be positive")
    if not value:
        return value, False
    if value.isascii() and max_cluster_codepoints >= 2:
        scan_limit = (
            len(value) if max_codepoints is None else min(len(value), max_codepoints)
        )
        if (
            scan_limit < len(value)
            and scan_limit > 0
            and value[scan_limit - 1] == "\r"
            and value[scan_limit] == "\n"
        ):
            scan_limit -= 1
        cluster_count = 0
        index = 0
        while index < scan_limit:
            next_index = (
                index + 2
                if value[index] == "\r"
                and index + 1 < scan_limit
                and value[index + 1] == "\n"
                else index + 1
            )
            cluster_count += 1
            if max_clusters is not None and cluster_count >= max_clusters:
                if next_index < len(value):
                    return value[:next_index], True
            index = next_index
        if scan_limit < len(value):
            return value[:scan_limit], True
        return value, False

    cluster_start = 0
    completed_clusters = 0
    cluster: list[str] = []
    for index, character in enumerate(value):
        if max_codepoints is not None and index >= max_codepoints:
            if cluster and _should_break(cluster, character):
                return value[:index], True
            return value[:cluster_start], True
        if cluster and _should_break(cluster, character):
            completed_clusters += 1
            if max_clusters is not None and completed_clusters >= max_clusters:
                return value[:index], True
            cluster_start = index
            cluster = []
        elif len(cluster) >= max_cluster_codepoints:
            return value[:cluster_start], True
        cluster.append(character)
    return value, False


def iter_grapheme_clusters(value: str) -> Iterator[str]:
    """Yield Unicode extended grapheme clusters using UAX #29 rules."""

    if not value:
        return

    if value.isascii():
        index = 0
        while index < len(value):
            character = value[index]
            if character == "\r" and index + 1 < len(value) and value[index + 1] == "\n":
                yield "\r\n"
                index += 2
                continue
            yield character
            index += 1
        return

    cluster: list[str] = []
    for character in value:
        if cluster and _should_break(cluster, character):
            yield "".join(cluster)
            cluster = []
        cluster.append(character)
    if cluster:
        yield "".join(cluster)
