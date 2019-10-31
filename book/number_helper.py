import re

class NumberHelper:
    @staticmethod
    def is_valid_roman_numeral(s: str):
        pattern = "^M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$"
        if s.strip():
            if re.search(pattern, s.upper()):
                return True
        return False

    @staticmethod
    def roman_to_int(s)->int:
        if NumberHelper.is_valid_roman_numeral(s):
            ss = s.upper()
            rom_val = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
            int_val: int = 0
            for i in range(len(ss)):
                if i > 0 and rom_val[ss[i]] > rom_val[ss[i - 1]]:
                    int_val += rom_val[ss[i]] - 2 * rom_val[ss[i - 1]]
                else:
                    int_val += rom_val[ss[i]]
            return int_val
        else:
            return 0

    @staticmethod
    def int_to_roman(num)->str:
        val = [
            1000, 900, 500, 400,
            100, 90, 50, 40,
            10, 9, 5, 4,
            1
        ]
        syb = [
            "M", "CM", "D", "CD",
            "C", "XC", "L", "XL",
            "X", "IX", "V", "IV",
            "I"
        ]
        roman_num = ''
        i = 0
        while num > 0:
            for _ in range(num // val[i]):
                roman_num += syb[i]
                num -= val[i]
            i += 1
        return roman_num
