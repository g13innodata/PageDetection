import re
import xml.etree.ElementTree as ET
from .words import Word

from .number_helper import NumberHelper
from collections import OrderedDict

# updates:
# Nov 28: Eliminate non-numeric and non-roman words

class Object:
    def __init__(self):
        self.object_element = None
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
        self.confidence = 0
        self.page_height = 0
        self.page_height = 0
        self.page_width = 0
        self.has_valid_leaf_no = True

        self.debug_page = []
        self.debug_conf = []

    def load_object(self, object_element: ET.Element):
        self.object_element = object_element
        param_page = object_element.find("PARAM[@name='PAGE']")
        try:
            self.page_height = int(object_element.attrib["height"])
        except:
            pass
        try:
            self.page_width = int(object_element.attrib["width"])
        except:
            pass
        if param_page is not None:
            if param_page != -1:
                page_value = param_page.attrib["value"].lower()
                if "." in page_value:
                    page_value = page_value[0:page_value.rindex(".")]

                split_ = page_value.split("_")
                try:
                    self.leaf_number = int(split_[len(split_) - 1])
                except():
                    self.leaf_number = 0

                self.has_valid_leaf_no = False if self.leaf_number == 0 else True

    # for testing purposes
    def load_test(self, leaf_number, ocr_value):
        self.leaf_number = leaf_number
        ocrs = ocr_value.split(', ')
        ctr =0
        for ocr in ocrs:
            ctr += 1
            if ctr == 1:
                self.text_UL = ocr
            elif ctr == 2:
                self.text_UM = ocr
            elif ctr == 3:
                self.text_UR = ocr
            elif ctr == 4:
                self.text_LL = ocr
            elif ctr == 5:
                self.text_LM = ocr
            elif ctr == 6:
                self.text_LR = ocr

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

        self.min_word_y2 = int(min_y2) + 20 if int(min_y2) != 100000 else 0 #+20 is used for skewed images
        self.max_word_y1 = int(max_y1) - 20 #-20 is used for skewed images

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
        return list(filter(None,OrderedDict((k, None) for k in x)))

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

    def predict_page_printed_number(self, object_list, last_page_detected):
        result = ""
        index = object_list.index(self)
        max_1_8 = int(len(object_list) / 8)
        next_index = index + 1
        if index < len(object_list):
            # for greater than last_page_detected
            for text in self.texts():
                if NumberHelper.is_numeric(text):
                    if int(text) > last_page_detected:
                        expected_next_printed_page = str(int(text) + 1)
                        if self.is_next_page_matched(object_list[next_index], expected_next_printed_page):
                            self.expected_next_printed_page = expected_next_printed_page
                            result = text
                            break
            # for less than last_page_detected
            else:
                for text in self.texts():
                    if NumberHelper.is_numeric(text):
                        expected_next_printed_page = str(int(text) + 1)
                        if self.is_next_page_matched(object_list[next_index], expected_next_printed_page):
                            self.expected_next_printed_page = expected_next_printed_page
                            result = text
                            break

        #added 11-MAR-2020
        if result == "1":
            if last_page_detected == 0 or index < max_1_8:
                result = ""

        if not result and index > 0:
            previous_object = object_list[index-1]
            tmp = previous_object.get_next_candidate()
            for text in self.texts():
                if NumberHelper.is_numeric(text):
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
        if val == None:
            val = ""
        if NumberHelper.is_numeric(val):
            return str(int(val) + 1)
        elif NumberHelper.is_valid_roman_numeral(val):
            return ""

    def is_next_page_matched(self, object, next_number):
        result = False
        if object.predicted_page_temp != "":
            if object.predicted_page_temp == str(next_number):
                result = True
        else:
            for text in object.texts():
                if text == next_number:
                    result = True
                    break
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
    def __filter_text(self, str):

        result = str.replace('[', '') \
            .replace(']', '') \
            .replace('.','') \
            .replace('.', '') \
            .replace(';', '') \
            .replace('*', '') \
            .replace('(', '') \
            .replace(')', '')
        if NumberHelper.is_numeric(result):
            # validate if greater than the leaf number
            if int(result) == 0:
                result = ""
        elif not self.__has_numeric_character(result) and not NumberHelper.is_valid_roman_numeral(result):
            result = ""
        elif self.__has_numeric_character(result) and not NumberHelper.is_valid_roman_numeral(result):
            result = result.replace('i', '1')
            result = result.replace('l', '1')
            result = result.replace('O', '0')
            result = result.replace('o', '0')
            result = result.replace('!', '1')
            result = result.replace('J', '9')

        if not NumberHelper.is_numeric(result) and not NumberHelper.is_valid_roman_numeral(result):
            result = ""

        result = result.strip()
        return result

    # Extract the upper leftmost text without upper interference.
    def __extract_text_UL(self):
        result = ""
        min_x1 = 0
        min_y1 = self.page_height
        if min_y1 == 0:
            min_y1 = 1000

        if self.min_word_y2 > 0:
            for word in self.word_list:
                if word.y1 <= self.min_word_y2 and (min_x1 == 0 or min_x1 < word.x1) \
                        and not word.has_inteterferring_text_upwards(self.word_list):
                    if self.page_width == 0 or (self.page_width > 0 and word.x1 <= self.page_width / 2):
                        result = word.text
                        min_x1 = word.x1
                    else:
                        pass
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
                    if self.page_width == 0 or (self.page_width>0 and word.x1 >= self.page_width / 2):
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
                    if self.page_width == 0 or (self.page_width > 0 and word.x1 <= self.page_width / 2):
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
                    if self.page_width == 0 or (self.page_width > 0 and word.x1 >= self.page_width / 2):
                        result = word.text
                        max_x2 = word.x2

        result = self.__filter_text(result)
        return result


    # Start: added 4/21/2021
    def remove_noise_pages(self, pg):
        if self.text_UL == pg:
            self.text_UL = ""
        if self.text_UM == pg:
            self.text_UM = ""
        if self.text_UR == pg:
            self.text_UR = ""
        if self.text_LL == pg:
            self.text_LL = ""
        if self.text_LM == pg:
            self.text_LM = ""
        if self.text_LR == pg:
            self.text_LR = ""


    def remove_noise_above_1500(self):
        if NumberHelper.is_numeric(self.text_UL):
            if int(self.text_UL) > 1500:
                self.text_UL = ""
        if NumberHelper.is_numeric(self.text_UM):
            if int(self.text_UM) > 1500:
                self.text_UM = ""
        if NumberHelper.is_numeric(self.text_UR):
            if int(self.text_UR) > 1500:
                self.text_UR = ""
        if NumberHelper.is_numeric(self.text_LL):
            if int(self.text_LL) > 1500:
                self.text_LL = ""
        if NumberHelper.is_numeric(self.text_LM):
            if int(self.text_LM) > 1500:
                self.text_LM = ""
        if NumberHelper.is_numeric(self.text_LR):
            if int(self.text_LR) > 1500:
                self.text_LR = ""

    # End: added 4/21/2021
