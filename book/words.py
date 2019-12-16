import xml.etree.ElementTree as ET

class Word:
    def __init__(self, word_element: ET.Element):
        coords = word_element.attrib["coords"].split(",")
        self.x1 = int(coords[0])
        self.y2 = int(coords[1])
        self.x2 = int(coords[2])
        self.y1 = int(coords[3])
        self.text = word_element.text

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
