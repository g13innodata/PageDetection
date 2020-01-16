import re
import xml.etree.ElementTree as ET
from .words import Word

from .number_helper import NumberHelper
from collections import OrderedDict

# updates:
# Nov 28: Eliminate non-numeric and non-roman words

class Object:
    def __init__(self, object_element: ET.Element):
        self.object_element = object_element
        self.predicted_page_temp = ""
        self.word_list = []
        self.candidate_printed_page = ""
        self.expected_next_printed_page = ""
        self.text_UL = ""
        self.text_UM = ""
        self.text_UR = ""
        self.text_LL = ""
        self.text_LM = ""
        self.text_LR = ""
        self.max_word_y1 = int(0)
        self.min_word_y2 = int(0)
        self.sure_prediction = False

        param_page = object_element.find("PARAM[@name='PAGE']")
        if param_page is not None:
            page_value = param_page.attrib["value"]
            page_value = page_value[0:page_value.index(".")]
            split_ = page_value.split("_")
            self.leaf_number = int(split_[len(split_)-1])

    # extract all the WORD tags and put it in a list
    def extract_words(self):
        min_y2 = int(100000)
        max_y1 = int(0)
        for word_element in self.object_element.iter('WORD'):
            word = Word(word_element)
            if word.is_page_candidate:
                min_y2 = int(word.y2) if int(word.y2) < int(min_y2) else int(min_y2)
                max_y1 = int(word.y1) if int(word.y1) > int(max_y1) else int(max_y1)
                self.word_list.append(word)

        self.min_word_y2 = int(min_y2) if int(min_y2) != 100000 else 0
        self.max_word_y1 = int(max_y1)

    def extract_possible_page_numbers(self):
        self.text_UL = self.__extract_text_UL()
        self.text_UM = self.__extract_text_UM()
        self.text_UR = self.__extract_text_UR()
        self.text_LL = self.__extract_text_LL()
        self.text_LM = self.__extract_text_LM()
        self.text_LR = self.__extract_text_LR()

    def texts(self):
        x = [
            self.text_UL,
            self.text_UM,
            self.text_UR,
            self.text_LL,
            self.text_LM,
            self.text_LR
        ]

        return list(OrderedDict((k, None) for k in x))
        # return list(dict.fromkeys(filter(None, x)))

    def texts_lower(self):
        x = [
            self.text_UL.lower(),
            self.text_UM.lower(),
            self.text_UR.lower(),
            self.text_LL.lower(),
            self.text_LM.lower(),
            self.text_LR.lower()
        ]
        return list(dict.fromkeys(filter(None, x)))

    def predict_page_printed_number(self, object_list):
        result = ""
        index = object_list.index(self)
        next_index = index + 1
        if index < len(object_list):
            for text in self.texts():
                if text.isnumeric():
                    expected_next_printed_page = str(int(text) + 1)
                    if self.__is_next_page_matched(object_list[next_index], expected_next_printed_page):
                        self.expected_next_printed_page = expected_next_printed_page
                        result = text
                        break
            else:
                result = ""
        if not result and index > 0:
            previous_object = object_list[index-1]
            tmp = previous_object.get_next_candidate()
            for text in self.texts():
                if text.isnumeric():
                    if text == tmp:
                        result = text
                        break
            else:
                self.candidate_printed_page = previous_object.get_next_candidate()

        self.predicted_page_temp = result

    def get_next_candidate(self):
        val = self.predicted_page_temp
        if not val:
            val = self.candidate_printed_page
        if val is None:
            val = ""
        if val.isnumeric():
            return str(int(val) + 1)
        elif NumberHelper.is_valid_roman_numeral(val):
            return ""

    def __is_next_page_matched(self, object, next_number):
        for text in object.texts():
            if text == next_number:
                result = True
                break
        else:
            result = False
        return result

    def __has_numeric_character(self, str):
        pattern = '[0-9]'
        if re.search(pattern, str.upper()):
            return True
        else:
            return False

    # This will filter that text should be:
    # 1. Numeric but the number should be less than or equal to the leaf number
    # 2. Should have at least 1 numeric character or is a valid roman numeral
    def __filter_text(self,str):

        result = str.replace('[', '').replace(']', '')
        if result.isnumeric():
            # validate if greater than the leaf number
            if int(result) > self.leaf_number or int(result) == 0:
                result = ""
        elif not self.__has_numeric_character(result) and not NumberHelper.is_valid_roman_numeral(result):
            result = ""
        elif self.__has_numeric_character(result) and not NumberHelper.is_valid_roman_numeral(result):
            result = result.replace('i', '1')
            result = result.replace('l', '1')
            result = result.replace('O', '0')
            result = result.replace('o', '0')
            result = result.replace('!', '1')



        result = result.strip()
        return result

    # Extract the upper leftmost text without upper interference.
    def __extract_text_UL(self):
        result = ""
        min_x1 = 0
        if self.min_word_y2 > 0:
            for word in self.word_list:
                if word.y1 <= self.min_word_y2 and (min_x1 == 0 or min_x1 < word.x1) \
                        and not word.has_inteterferring_text_upwards(self.word_list):
                    result = word.text
                    min_x1 = word.x1
        result = self.__filter_text(result)
        return result

    # Extract the topmost text.
    def __extract_text_UM(self):
        result = ""
        min_x1 = 0
        if self.min_word_y2 > 0:
            for word in self.word_list:
                if word.y1 <= self.min_word_y2 and (min_x1 == 0 or min_x1 < word.x1):
                    result = word.text
                    min_x1 = word.x1
        result = self.__filter_text(result)
        return result

    # Extract the upper rightmost text without upper interference.
    def __extract_text_UR(self):
        result = ""
        max_x2 = 0
        if self.min_word_y2 > 0:
            for word in self.word_list:
                if word.y1 <= self.min_word_y2 \
                        and (max_x2 == 0 or max_x2 > word.x2) \
                        and not word.has_inteterferring_text_upwards(self.word_list):
                    result = word.text
                    max_x2 = word.x2
        result = self.__filter_text(result)
        return result

    # Extract the lower leftmost text without lower interference.
    def __extract_text_LL(self):
        result = ""
        min_x1 = 0
        if self.min_word_y2 > 0:
            for word in self.word_list:
                if word.y2 >= self.max_word_y1 \
                        and (min_x1 == 0 or min_x1 < word.x1) \
                        and not word.has_inteterferring_text_downwards(self.word_list):
                    result = word.text
                    min_x1 = word.x1
        result = self.__filter_text(result)
        return result

    # Extract the lowermost text
    def __extract_text_LM(self):
        result = ""
        min_x1 = 0
        if self.min_word_y2 > 0:
            for word in self.word_list:
                if word.y2 >= self.max_word_y1 and (min_x1 == 0 or min_x1 < word.x1):
                    result = word.text
                    min_x1 = word.x1
        result = self.__filter_text(result)
        return result

    # Extract the lower rightmost text without lower interference.
    def __extract_text_LR(self):
        result = ""
        max_x2 = 0
        if self.min_word_y2 > 0:
            for word in self.word_list:
                if word.y2 >= self.max_word_y1 \
                        and (max_x2 == 0 or max_x2 > word.x2) \
                        and not word.has_inteterferring_text_downwards(self.word_list):
                    result = word.text
                    max_x2 = word.x2
        result = self.__filter_text(result)
        return result
