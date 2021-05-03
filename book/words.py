import xml.etree.ElementTree as ET
import re
from .number_helper import NumberHelper


class Word:
    def __init__(self, word_element: ET.Element):
        self.is_page_candidate = False
        # start: added 4/30/2021
        if 'coords' not in word_element.attrib:
            return
        # end: added 4/30/2021
        coords = word_element.attrib["coords"].split(",")
        self.x1 = int(coords[0])
        self.y2 = int(coords[1])
        self.x2 = int(coords[2])
        self.y1 = int(coords[3])
        self.text = word_element.text.strip()
        if len(self.text) <= 5:
            if NumberHelper.is_valid_roman_numeral(self.text):
                self.is_page_candidate = True
            elif bool(re.search(r'\d', self.text)):
                self.is_page_candidate = True

    def has_inteterferring_text_upwards(self, word_list):
        for word in word_list:
            if word is not self:
                if word.y1 < self.y2 and (word.x1 in range(self.x1, self.x2) or
                                          word.x2 in range(self.x1, self.x2)):
                    return True
        else:
            return False

    def has_inteterferring_text_downwards(self, word_list):
        for word in word_list:
            if word is not self:
                if word.y2 > self.y2 and (word.x1 in range(self.x1, self.x2) or
                                          word.x2 in range(self.x1, self.x2)):
                    return True
        else:
            return False
