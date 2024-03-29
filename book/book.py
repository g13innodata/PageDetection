import xml.etree.cElementTree as ET
import json
import os
import re
import sys
from .object import Object
from .number_helper import NumberHelper
from .scan_data import ScanData


class Book:
    def __init__(self):
        # tree = ET.parse(xml_filename)
        # root = tree.getroot()
        self.xml_filename = None
        self.object_list = []
        self.blank_gap_dictionary = {}
        self.last_blank_start = 0
        self.has_valid_leaf_no = True

        # Markers for debugging
        # self.update_0506 = False

    def load_xml(self, xml_filename):
        self.xml_filename = xml_filename
        expected_leaf_no = 1
        for event, object_element in ET.iterparse(xml_filename):
            if object_element.tag != "OBJECT":
                continue

            object_ = Object()
            object_.load_object(object_element)
            if object_.leaf_number == 0:
                continue
            # Start: added 4/23/2020
            # Terminate the application once a page has encountered an invalid leaf no
            self.has_valid_leaf_no = object_.has_valid_leaf_no
            if not self.has_valid_leaf_no:
                break
            # End: added 4/23/2020

            object_.extract_words()
            object_.extract_possible_page_numbers()
            # Start: added 2/14
            if object_.leaf_number != expected_leaf_no:
                for i in range(expected_leaf_no, object_.leaf_number):
                    t_object = Object()
                    t_object.leaf_number = i
                    self.object_list.append(t_object)
            # End: added 2/14
            self.object_list.append(object_)
            expected_leaf_no = object_.leaf_number + 1

        # Start: added 4/23/2020
        # Terminate the application once a page has invalid leaf no
        if not self.has_valid_leaf_no:
            return
        # End: added 4/23/2020
        self.__start_prediction()

        # Start: added 4/21/2021
        # Remove noise if zero confidence and try to do second round prediction
        if self.__is_all_zero_confidence():
            self.__remove_noise_page_numbers()
            self.__start_prediction()
        # End: added 4/21/2021

    # Start: Added 4/21/2021
    def __is_all_zero_confidence(self):
        result = True
        for obj in self.object_list:
            if obj.confidence > 0:
                result = False
                break
        return result

    def __remove_noise_page_numbers(self):
        dictionary_pages = {}
        # pages 1-1000; 1001-2000; 2001 and up
        dictionary_ranges = {1: 0, 1501: 0}
        max_below_1500 = 0
        below_1000 = 0
        for obj in self.object_list:
            obj.predicted_page_temp = ""
            for pg in obj.texts():
                if pg in dictionary_pages:
                    dictionary_pages[pg] += 1
                else:
                    dictionary_pages[pg] = 1
        for key, value in sorted(dictionary_pages.items(), key=lambda item: item[1], reverse=True):
            # remove any probable ocr page numbers that repeats more than twice
            if NumberHelper.is_numeric(str(key)):
                if int(key) > 1500:
                    dictionary_ranges[1501] += 1
                else:
                    dictionary_ranges[1] += 1
                    if int(key) > max_below_1500:
                        max_below_1500 = int(key)
                    if int(key) < 1000:
                        below_1000 += 1
            if value > 2:
                for obj in self.object_list:
                    obj.remove_noise_pages(key)
        if dictionary_ranges[1501] < dictionary_ranges[1]:
            if below_1000 > dictionary_ranges[1] * .9 or 1500-max_below_1500 > 200:
                for obj in self.object_list:
                    obj.remove_noise_above_1500()
    # End: added 4/21/2021

    def load_test(self, test_file_name):
        self.xml_filename = test_file_name
        f = open(test_file_name, 'r')
        content = f.read()
        f.close()
        splits = content.split("Scandata says:")
        expected_leaf_no = 1
        for split in splits:
            leaf_num = 0
            ocr_value = ""
            start_capture_ocr = False
            lines = split.split("\n")
            for line in lines:
                if start_capture_ocr:
                    ocr_value = line
                    start_capture_ocr = False
                if line.startswith("Leaf number: "):
                    leaf_num = int(line.replace("Leaf number: ", ""))
                elif line == "OCR Value:":
                    start_capture_ocr = True
            if leaf_num != 0:
                object_ = Object()
                object_.load_test(leaf_num, ocr_value)
                if object_.leaf_number != expected_leaf_no:
                    for i in range(expected_leaf_no, object_.leaf_number):
                        t_object = Object("")
                        t_object.leaf_number = i
                        self.object_list.append(t_object)
                # End: added 2/14
                self.object_list.append(object_)
                expected_leaf_no = object_.leaf_number + 1
        self.__start_prediction()

    def __start_prediction(self):
        self.csv_header = 'Leaf,OCR'
        # STEP 1: do prediction based on previous, current, and next page

        self.__perform_initial_prediction()
        self.__debug_note_pages('Pred1')

        # STEP 2: do fill-up gaps
        self.__perform_fillup_gaps_arabic()
        # STEP 3: generate confidence +10 and -10 sequence
        self.__build_page_confidence()
        self.__debug_note_pages('GAP1')

        self.__perform_fillup_gaps_0_confidence(True)
        self.__debug_note_pages('GAP2C')

        # STEP 4: updating roman numerals pages
        # self.__perform_fillup_roman_numerals()
        # self.__debug_note_pages('RomanN')

        # STEP 5: fill up blank possible numeric values, from start, from end and between
        self.__perform_fillup_numeric_blanks_update_confidence()
        self.__cleanup_front_matter_noise()
        self.__cleanup_in_mid_wild_numbers_between_100()
        self.__debug_note_pages('Blanks')

        # STEP 4: updating roman numerals pages
        self.__perform_fillup_roman_numerals()
        self.__debug_note_pages('RomanN')

        # STEP 6: in a case no page numbers predicted at all, use the leaf number
        self.__perform_fillup_no_page_numbers()

        # STEP 7: added additional validation for zero confidence (all pages) results (twice)
        self.__perform_zero_confidence_fix()
        self.__perform_zero_confidence_fix()
        self.__perform_nonzero_confidence_fix()
        self.__debug_note_pages('Orig')
        # STEP 8: granular confidence
        self.__perform_granular_confidence()

        self.__debug_note_pages('Granular')

        # Notes: Disable this line in Production mode
        #        This is to generate CSV file for analysis
        # self.__print_pages("After final prediction!")

    def __debug_note_pages(self, header):
        self.csv_header += ',' + header + ',Conf'
        for obj in self.object_list:
            obj.debug_page.append(obj.predicted_page_temp)
            obj.debug_conf.append(obj.confidence)

    # temporary routine to print details in the console
    def __print_pages(self, caption):
        application_path = os.path.dirname(self.xml_filename)
        csv_file_name = self.xml_filename.lower().replace("_djvu.xml", "_debug")
        # if self.update_0506:
        #    csv_file_name = csv_file_name + "_checkme"
        csv_file_name += ".csv"
        # csv_file_name = os.path.join(application_path, os.path.filena "debug.csv")
        f = open(csv_file_name, 'w+')
        # csv_line = 'Leaf,OCR, Initial,Conf, GAP1,Conf,GAP2C, Conf, Roman, Conf, Blanks, Conf\n'
        f.write(self.csv_header + '\n')
        prev_page = 0
        for obj in self.object_list:
            if NumberHelper.is_numeric(obj.predicted_page_temp):
                prev_page = int(obj.predicted_page_temp)
            csv_line = str(obj.leaf_number) + ',"[' + ','.join(obj.texts()) + ']"'
            for i in range(0, len(obj.debug_page)):
                csv_line = csv_line + ',' + str(obj.debug_page[i]) + ',' + str(obj.debug_conf[i])

            csv_line = csv_line + '\n'

            '''           + obj.debug_page_step1 + ',' +\
                       obj.debug_page_step2 + ',' + str(obj.debug_confidence_orig) + ',' +\
                       obj.debug_page_step3 + ',' + obj.debug_page_step4 + ',' + obj.debug_page_step5 + ',' + \
                       obj.predicted_page_temp + ',' + \
                       str(page_diff) + ',' + \
                       str(obj.confidence) + ',' + conf_change + '\n' '''
            f.write(csv_line)
        f.close()

    # Perform temporary prediction, filling up objects (predicted_page_temp and
    # expected_next_printed_page).
    def __perform_initial_prediction(self):
        blank_start = -1
        blank_end = -1
        all_blanks = True
        last_page_detected = 0
        for i in range(0, len(self.object_list) - 1):
            self.object_list[i].predict_page_printed_number(self.object_list, last_page_detected)
            if not self.object_list[i].predicted_page_temp:
                if blank_start == -1:
                    blank_start = i
                blank_end = i
            else:
                last_page_detected = int(self.object_list[i].predicted_page_temp)
                all_blanks = False
                if blank_start != -1:
                    self.blank_gap_dictionary[blank_start] = blank_end
                    blank_start = -1
                    blank_end = -1
                    blank_end = -1
        if blank_start != -1:
            self.blank_gap_dictionary[blank_start] = blank_end + 1

        self.__perform_temporary_prediction_forward()

    def __perform_temporary_prediction_forward(self):
        for i in range(0, len(self.object_list) - 2):
            gap = 1
            if self.object_list[i].predicted_page_temp == "":
                for j in range(i + 1, len(self.object_list) - 2):
                    for text in self.object_list[i].texts():
                        if NumberHelper.is_numeric(text):
                            expected_next_printed_page = str(int(text) + gap)
                            if self.object_list[i].is_next_page_matched(self.object_list[j],
                                                                        expected_next_printed_page):
                                self.object_list[i].predicted_page_temp = text
                                self.object_list[j].predicted_page_temp = expected_next_printed_page
                                break
                    gap += 1
                    if gap > 10:
                        break
        blank_start = -1
        blank_end = -1
        self.blank_gap_dictionary.clear()
        for i in range(0, len(self.object_list) - 1):
            if not self.object_list[i].predicted_page_temp:
                if blank_start == -1:
                    blank_start = i
                blank_end = i
            else:
                if blank_start != -1:
                    self.blank_gap_dictionary[blank_start] = blank_end
                    blank_start = -1
                    blank_end = -1
        if blank_start != -1:
            self.blank_gap_dictionary[blank_start] = blank_end + 1

    def __perform_fillup_gaps_arabic(self):
        matched_keys = []
        for key in self.blank_gap_dictionary:
            if key > 0:
                blank_start = key
                blank_end = self.blank_gap_dictionary[key]
                start_candidate = self.object_list[blank_start].candidate_printed_page
                if start_candidate == None:
                    start_candidate = ""
                end_candidate = self.object_list[blank_end].candidate_printed_page
                if NumberHelper.is_numeric(start_candidate) and NumberHelper.is_numeric(end_candidate):
                    if str(int(start_candidate) - 1) == self.object_list[blank_start - 1].predicted_page_temp \
                            and str(int(end_candidate) + 1) == self.object_list[blank_end + 1].predicted_page_temp:
                        for i in range(blank_start, blank_end + 1):
                            self.object_list[i].predicted_page_temp = self.object_list[i].candidate_printed_page
                            self.object_list[i].sure_prediction = True
                        matched_keys.append(key)

        # Remove successfully matched
        for key in matched_keys:
            self.blank_gap_dictionary.pop(key)

    # building confidence
    def __build_page_confidence(self):
        required_count = 10
        if len(self.object_list) <= 15:
            required_count = 3
        elif len(self.object_list) <= 35:
            required_count = 5

        # required_count = 10
        # forward: N(required_count) out of 20 forward
        for obj in self.object_list:
            if obj.confidence == 0:
                obj.confidence = self.__get_confidence_forward(obj.leaf_number, obj.predicted_page_temp, required_count)
                obj.debug_confidence_orig = obj.confidence
        # backward: 10 out of 20 backward
        for i in range(len(self.object_list) - 1, 0, -1):
            if self.object_list[i].confidence == 0:
                self.object_list[i].confidence = self.__get_confidence_backward(self.object_list[i].leaf_number,
                                                                                self.object_list[i].predicted_page_temp,
                                                                                required_count)
                self.object_list[i].debug_confidence_orig = self.object_list[i].confidence

        # Set confidence to 100
        # - Previous page is 100 and current page is 0
        # - page number prediction is found in the texts()
        # - page number is +1 from previous
        for i in range(1, len(self.object_list)):
            if self.object_list[i].confidence == 0 and self.object_list[i - 1].confidence == 100 and \
                    NumberHelper.is_numeric(self.object_list[i].predicted_page_temp) and \
                    NumberHelper.is_numeric(self.object_list[i - 1].predicted_page_temp):
                if self.object_list[i].predicted_page_temp in self.object_list[i].texts() and \
                        int(self.object_list[i].predicted_page_temp) == int(self.object_list[i - 1].predicted_page_temp) \
                        + 1:
                    self.object_list[i].confidence = 100
                    self.object_list[i].debug_confidence_orig = self.object_list[i].confidence
        # Set confidence to 100
        #    - Next page is 100 and current page is 0
        #    - page number prediction is found in the texts()
        #    - page number is -1 from next
        for i in range(len(self.object_list) - 2, -1, -1):
            if self.object_list[i].confidence == 0 and self.object_list[i + 1].confidence == 100 and \
                    NumberHelper.is_numeric(self.object_list[i].predicted_page_temp) and \
                    NumberHelper.is_numeric(self.object_list[i + 1].predicted_page_temp):
                if self.object_list[i].predicted_page_temp in self.object_list[i].texts() and \
                        int(self.object_list[i].predicted_page_temp) == int(self.object_list[i + 1].predicted_page_temp) \
                        - 1:
                    self.object_list[i].confidence = 100
                    self.object_list[i].debug_confidence_orig = self.object_list[i].confidence
        # Set confidence to 0
        # - 100, 100, 100
        # - last = first + 2
        # - mid <> first + 1
        for i in range(1, len(self.object_list) - 1):
            o_prev = self.object_list[i - 1]
            o_current = self.object_list[i]
            o_next = self.object_list[i + 1]
            if o_prev.confidence == 100 and o_current.confidence == 100 and o_next.confidence == 100:
                if int(o_prev.predicted_page_temp) + 2 == int(o_next.predicted_page_temp) and \
                        int(o_prev.predicted_page_temp) + 1 != int(o_current.predicted_page_temp):
                    self.object_list[i].confidence = 0
                    self.object_list[i].debug_confidence_orig = self.object_list[i].confidence

        # Added 10-MAR-2019
        # 100, 0, 0, 102 or 100,0,0,0,0,105
        for i in range(0, len(self.object_list)):
            if self.object_list[i].confidence == 100:
                next_page = int(self.object_list[i].predicted_page_temp) + 1
                for j in range(i + 1, len(self.object_list)):
                    if self.object_list[j].confidence == 0:
                        if str(next_page) in self.object_list[j].texts():
                            self.object_list[j].predicted_page_temp = str(next_page)
                            self.object_list[j].confidence = 100
                            self.object_list[j].debug_confidence_orig = self.object_list[j].confidence
                    else:
                        break
                    next_page += 1

    # set the leaf number to 100% confidence if it can match to the next max_match
    def __get_confidence_forward(self, leaf_number, page_number, max_match):
        result = 0
        if NumberHelper.is_numeric(page_number):
            match_counter = 0
            expected_page_number = int(page_number) + 1
            for i in range(leaf_number, len(self.object_list)):
                if self.object_list[i].predicted_page_temp == str(expected_page_number):
                    match_counter = match_counter + 1
                expected_page_number = expected_page_number + 1
                if match_counter >= max_match:
                    result = 100
                if i > leaf_number + (max_match * 2):
                    break
        return result

    # set the leaf number to 100% confidence if it can match to the previous max_match
    def __get_confidence_backward(self, leaf_number, page_number, max_match):
        result = 0

        if NumberHelper.is_numeric(page_number):
            match_counter = 0
            expected_page_number = int(page_number) - 1
            for i in range(leaf_number - 2, 0, -1):
                if self.object_list[i].predicted_page_temp == str(expected_page_number):
                    match_counter = match_counter + 1
                expected_page_number = expected_page_number - 1
                if match_counter >= max_match:
                    result = 100
                    break
                if i < leaf_number - (max_match * 2):
                    break
        return result

    def __perform_fillup_gaps_0_confidence(self, is_set_100):
        blank_start = -1
        blank_end = 0

        for i in range(0, len(self.object_list) - 1):
            obj = self.object_list[i]
            if obj.confidence == 0:
                if blank_start == -1:
                    blank_start = i
                    blank_end = i
                else:
                    blank_end = i
            else:
                if blank_start >= 0 and blank_end >= 0:
                    printed_start = 0
                    if blank_start > 0:
                        printed_start = int(self.object_list[blank_start - 1].predicted_page_temp)
                    printed_end = int(self.object_list[blank_end + 1].predicted_page_temp)
                    if ((printed_end - printed_start) - 2) == (blank_end - blank_start):
                        page_number = printed_start + 1
                        for j in range(blank_start, blank_end + 1):
                            self.object_list[j].predicted_page_temp = str(page_number)
                            if is_set_100:
                                self.object_list[j].confidence = 100
                            page_number = page_number + 1
                    else:
                        # should solve 101,102,blank,blank,103,104,blank,blank,105,106
                        if not is_set_100:
                            for j in range(blank_start, blank_end + 1):
                                if NumberHelper.is_numeric(self.object_list[j].predicted_page_temp):
                                    if (int(self.object_list[j].predicted_page_temp) > printed_start) and \
                                            (int(self.object_list[j].predicted_page_temp) < printed_end):
                                        pass
                                    else:
                                        self.object_list[j].predicted_page_temp = ""
                                        self.object_list[j].confidence = 0
                    blank_start = -1
                    blank_end = 0

    # returns the index of first leaf with 100 confidence
    def __get_first_confidence_index_100(self):
        result = -1
        for i in range(0, len(self.object_list)):
            if self.object_list[i].confidence == 100:
                result = i
                break
        return result

    # returns the index of the last leaf with 100 confidence
    def __get_last_confidence_index_100(self):
        result = -1
        for i in range(len(self.object_list) - 1, 0, -1):
            if self.object_list[i].confidence == 100:
                result = i
                break
        return result

    # get the lower index that the page number matches with computed value from the starting index or idx100
    def __get_lower_index(self, idx100):
        result = -1
        if NumberHelper.is_numeric(self.object_list[idx100].predicted_page_temp):
            page_number_idx100 = int(self.object_list[idx100].predicted_page_temp)
            for i in range(idx100 - 1, -1, -1):
                if NumberHelper.is_numeric(self.object_list[i].predicted_page_temp):
                    page_number_lower = int(self.object_list[i].predicted_page_temp)
                    if page_number_lower < page_number_idx100:
                        if self.__get_confidence_backward(self.object_list[i].leaf_number,
                                                          self.object_list[i].predicted_page_temp,
                                                          2):
                            result = i
                            break
                        if page_number_idx100 - (idx100 - i) == page_number_lower:
                            result = i
                            break
        return result

    def __get_higher_index(self, idx100):
        result = -1
        page_number_idx100 = int(self.object_list[idx100].predicted_page_temp)
        for i in range(idx100 + 1, len(self.object_list)):
            if NumberHelper.is_numeric(self.object_list[i].predicted_page_temp):
                page_number_higher = int(self.object_list[i].predicted_page_temp)
                if page_number_higher > page_number_idx100:
                    if self.__get_confidence_forward(self.object_list[i].leaf_number,
                                                     self.object_list[i].predicted_page_temp,
                                                     2):
                        result = i
                        break
        return result

    def __perform_fillup_numeric_blanks_update_confidence(self):
        # first part
        # in between pages which has predicted out of range will be removed
        while True:
            idx = self.__get_first_confidence_index_100()
            if idx > 0:
                lower_idx = self.__get_lower_index(idx)
                if lower_idx != -1:
                    self.object_list[lower_idx].confidence = 100
                    pg_start = int(self.object_list[lower_idx].predicted_page_temp)
                    pg_end = int(self.object_list[idx].predicted_page_temp)
                    for i in range(lower_idx + 1, idx):
                        if NumberHelper.is_numeric(self.object_list[i].predicted_page_temp):
                            if not int(self.object_list[i].predicted_page_temp) in range(pg_start, pg_end):
                                self.object_list[i].predicted_page_temp = ""
                else:
                    break
            else:
                break

        # last part
        # in between pages which has predicted out of range will be removed
        while True:
            idx = self.__get_last_confidence_index_100()
            if idx != -1:
                higher_idx = self.__get_higher_index(idx)
                if higher_idx != -1:
                    self.object_list[higher_idx].confidence = 100
                    pg_start = int(self.object_list[idx].predicted_page_temp)
                    pg_end = int(self.object_list[higher_idx].predicted_page_temp)
                    for i in range(idx + 1, higher_idx):
                        if NumberHelper.is_numeric(self.object_list[i].predicted_page_temp):
                            if not int(self.object_list[i].predicted_page_temp) in range(pg_start, pg_end):
                                self.object_list[i].predicted_page_temp = ""
                else:
                    break
            else:
                break

        # gather gaps in between numeric pages and put in dictionary
        self.blank_gap_dictionary.clear()
        start_100 = -1
        blank_started = False
        for i in range(0, len(self.object_list)):
            if NumberHelper.is_numeric(self.object_list[i].predicted_page_temp):
                if blank_started == False:
                    start_100 = i
                elif blank_started == True:
                    self.blank_gap_dictionary[start_100] = i
                    start_100 = -1
                    blank_started = False
            if start_100 != -1 and not NumberHelper.is_numeric(self.object_list[i].predicted_page_temp):
                blank_started = True

        for blank in self.blank_gap_dictionary:
            # fix forward
            next_page = int(self.object_list[blank].predicted_page_temp) + 1
            for j in range(blank + 1, self.blank_gap_dictionary[blank]):
                if self.object_list[j].predicted_page_temp == "":
                    if str(next_page) in self.object_list[j].texts():
                        self.object_list[j].predicted_page_temp = str(next_page)
                next_page = next_page + 1

            # fix backward
            next_page = int(self.object_list[self.blank_gap_dictionary[blank]].predicted_page_temp) - 1
            for j in range(self.blank_gap_dictionary[blank] - 1, blank, -1):
                if self.object_list[j].predicted_page_temp == "":
                    if str(next_page) in self.object_list[j].texts():
                        self.object_list[j].predicted_page_temp = str(next_page)
                next_page = next_page - 1

            # previous or after that ends the last 2 or more characters
            if int(self.object_list[blank].predicted_page_temp) > 100:
                for j in range(blank, self.blank_gap_dictionary[blank] - 1):
                    if self.object_list[j].predicted_page_temp != "" and \
                            self.object_list[j + 1].predicted_page_temp == "":
                        next_page = int(self.object_list[j].predicted_page_temp) + 1
                        has_end_2 = False
                        has_end_1 = False
                        has_start_2 = False
                        for text in self.object_list[j + 1].texts():
                            if str(next_page).endswith(text):
                                if len(text) >= 2:
                                    has_end_2 = True
                                else:
                                    has_end_1 = True
                            if str(next_page).startswith(text):
                                if len(text) >= 2:
                                    has_start_2 = True
                        if has_end_2 or (has_start_2 and has_end_1):
                            self.object_list[j + 1].predicted_page_temp = str(next_page)

                for j in range(self.blank_gap_dictionary[blank], blank + 1, -1):
                    if self.object_list[j].predicted_page_temp != "" and \
                            self.object_list[j - 1].predicted_page_temp == "":
                        next_page = int(self.object_list[j].predicted_page_temp) - 1
                        has_end_2 = False
                        has_end_1 = False
                        has_start_2 = False
                        for text in self.object_list[j - 1].texts():
                            if str(next_page).endswith(text):
                                if len(text) >= 2:
                                    has_end_2 = True
                                else:
                                    has_end_1 = True
                            if str(next_page).startswith(text):
                                if len(text) >= 2:
                                    has_start_2 = True
                        if has_end_2 or (has_start_2 and has_end_1):
                            self.object_list[j - 1].predicted_page_temp = str(next_page)

                next_page = int(self.object_list[blank].predicted_page_temp) + 1
                for j in range(blank + 1, self.blank_gap_dictionary[blank]):
                    if self.object_list[j].predicted_page_temp == "":
                        has_end_2 = False
                        has_end_1 = False
                        has_start_2 = False
                        for text in self.object_list[j].texts():
                            if str(next_page).endswith(text):
                                if len(text) >= 2:
                                    has_end_2 = True
                                else:
                                    has_end_1 = True
                            if str(next_page).startswith(text):
                                if len(text) >= 2:
                                    has_start_2 = True
                        if has_end_2 or (has_start_2 and has_end_1):
                            self.object_list[j].predicted_page_temp = str(next_page)
                    next_page = next_page + 1

                next_page = int(self.object_list[self.blank_gap_dictionary[blank]].predicted_page_temp) - 1
                for j in range(self.blank_gap_dictionary[blank] - 1, blank, -1):
                    if self.object_list[j].predicted_page_temp == "":
                        has_end_2 = False
                        has_end_1 = False
                        has_start_2 = False
                        for text in self.object_list[j].texts():
                            if str(next_page).endswith(text):
                                if len(text) >= 2:
                                    has_end_2 = True
                                else:
                                    has_end_1 = True
                            if str(next_page).startswith(text):
                                if len(text) >= 2:
                                    has_start_2 = True
                        if has_end_2 or (has_start_2 and has_end_1):
                            self.object_list[j].predicted_page_temp = str(next_page)
                    next_page = next_page - 1

        # update blanks in sequence from last
        last_printed = ""
        for x in range(1, len(self.object_list)):
            if self.object_list[x].predicted_page_temp == "" and NumberHelper.is_numeric(last_printed):
                next_printed = int(last_printed) + 1
                self.object_list[x].predicted_page_temp = str(next_printed)
            last_printed = self.object_list[x].predicted_page_temp

        # backwards with 0 confidence
        for x in range(len(self.object_list) - 1, -1, -1):
            if self.object_list[x].confidence == 100:
                page_number = int(self.object_list[x].predicted_page_temp) + 1

                for j in range(x + 1, len(self.object_list)):
                    self.object_list[j].predicted_page_temp = str(page_number)
                    page_number += 1
                break

        # if it does not start with 1 from the top
        initial_count = 0
        for x in range(1, len(self.object_list)):
            initial_count += 1
            if NumberHelper.is_numeric(self.object_list[x].predicted_page_temp):
                if int(self.object_list[x].predicted_page_temp) < initial_count:
                    page_number = int(self.object_list[x].predicted_page_temp) - 1
                    if page_number >= 1:
                        for j in range(x - 1, -1, -1):
                            if page_number < 1:
                                # TEMPORARY: SET TO 0 INSTEAD OF 100
                                # self.object_list[j].confidence = 0
                                if NumberHelper.is_numeric(self.object_list[j].predicted_page_temp) or \
                                        self.object_list[j].predicted_page_temp == "":
                                    self.object_list[j].predicted_page_temp = ""
                                    # Added 8/14/2020
                                    self.object_list[j].confidence = 0
                            else:
                                self.object_list[j].predicted_page_temp = str(page_number)
                                self.object_list[j].confidence = 0
                            page_number -= 1
                break

        # Added 10-MAR-2019
        # 100, 0, 0, 102 or 100,0,0,0,0,105
        for i in range(0, len(self.object_list)):
            if self.object_list[i].confidence == 100:
                start_next_page = int(self.object_list[i].predicted_page_temp) + 1
                next_page = start_next_page
                for j in range(i + 1, len(self.object_list)):
                    if self.object_list[j].confidence == 0:
                        if str(next_page) in self.object_list[j].texts():
                            x_page = start_next_page
                            for k in range(i + 1, j + 1):
                                self.object_list[k].predicted_page_temp = str(x_page)
                                self.object_list[k].confidence = 100
                                x_page += 1
                            break
                    else:
                        break
                    next_page += 1

        # Added 10-MAR-2019
        # 100, 1, 2, 3, 4, 5, 6, 7, 8 change to 100 ... 108
        for i in range(0, len(self.object_list)):
            if NumberHelper.is_numeric(self.object_list[i].predicted_page_temp):
                start_next_page = int(self.object_list[i].predicted_page_temp) + 1
                next_page = start_next_page
                for j in range(i + 1, len(self.object_list)):
                    if self.object_list[j].confidence == 0 and NumberHelper.is_numeric(
                            self.object_list[j].predicted_page_temp):
                        if str(next_page).endswith(self.object_list[j].predicted_page_temp) and \
                                int(self.object_list[j].predicted_page_temp) < next_page:
                            self.object_list[j].predicted_page_temp = str(next_page)
                        else:
                            break
                    else:
                        break
                    next_page += 1

    def __perform_fillup_roman_numerals(self):
        max_leaf = int(len(self.object_list) / 8.0)
        blank_end = 0
        roman_count = 0
        for object_ in self.object_list:
            if not object_.predicted_page_temp:
                # blank_end += 1
                for text in object_.texts():
                    if NumberHelper.is_valid_roman_numeral(text):
                        roman_count += 1
                        break
            else:
                break
            blank_end += 1

        # Make sure that there are at least 3 roman numeral appearnaces.
        # Make sure that it belongs to the first 1/8 number of pages
        if roman_count >= 3 and blank_end < max_leaf:
            page = 0
            max_matched_count = 0
            max_matched_start = 0
            while page < blank_end:
                page += 1
                match_count = 0
                for i in range(page, blank_end):
                    roman_prediction = NumberHelper.int_to_roman((i - page) + 1).lower()
                    object_ = self.object_list[i]
                    if roman_prediction in object_.texts_lower():
                        match_count += 1
                if match_count > max_matched_count:
                    max_matched_count = match_count
                    max_matched_start = page
                if blank_end - page < max_matched_count:
                    break

            if max_matched_count >= 3:
                for page in range(max_matched_start, blank_end):
                    roman_prediction = NumberHelper.int_to_roman((page - max_matched_start) + 1).lower()
                    self.object_list[page].predicted_page_temp = roman_prediction

    # cleanup the front matter noise
    # Front matter is bellow 1/8 of the total number of pages. Ex: 50 out of 400 pages.
    def __cleanup_front_matter_noise(self):
        max_leaf = int(len(self.object_list) / 8.0)
        index_100 = self.__get_first_confidence_index_100()
        # initially 2 but don't work
        gap_leaf_tolerance = 10000

        if index_100 > 0 and index_100 <= max_leaf:
            base_page = int(self.object_list[index_100].predicted_page_temp)
            if index_100 > base_page:
                last_index = index_100
                if base_page > 1:
                    for i in range(last_index - 1, -1, -1):
                        last_index = i
                        base_page -= 1
                        self.object_list[i].predicted_page_temp = str(base_page)
                        if base_page == 1:
                            break
                for i in range(0, last_index):
                    self.object_list[i].predicted_page_temp = ""
            # simply remove > values
            else:
                base_index = 0
                gap_leaf = 1
                for i in range(index_100 - 1, -1, -1):
                    if NumberHelper.is_numeric(self.object_list[i].predicted_page_temp):
                        current_page = int(self.object_list[i].predicted_page_temp)
                        if current_page < base_page and base_page - current_page + gap_leaf_tolerance >= gap_leaf:
                            base_page = current_page
                            base_index = i
                            gap_leaf = 1
                        else:
                            self.object_list[i].predicted_page_temp = ""
                            gap_leaf += 1
                    else:
                        gap_leaf += 1

                for i in range(0, base_index):
                    self.object_list[i].predicted_page_temp = ""

                # Resequencing
                last_printed = ""
                for x in range(0, index_100):
                    if self.object_list[x].predicted_page_temp == "" and NumberHelper.is_numeric(last_printed):
                        next_printed = int(last_printed) + 1
                        self.object_list[x].predicted_page_temp = str(next_printed)
                    last_printed = self.object_list[x].predicted_page_temp

                # if not start with 1
                if base_page > -100 and base_index > 0:
                    for i in range(base_index, 0, -1):
                        next_printed = int(self.object_list[i].predicted_page_temp) - 1
                        if next_printed > 0:
                            self.object_list[i - 1].predicted_page_temp = str(next_printed)
                        else:
                            break

    # step 1: check if all 100% are in ascending order
    # step 2: check if the 100% is more than 50% of the total leafs
    # step 3: get the unsequence percentage, it should be within 5%
    # step 3: remove not in range in between 100s
    def __cleanup_in_mid_wild_numbers_between_100(self):
        prev_100 = 0
        count_100 = 0
        count_unseq = 0
        for obj_ in self.object_list:
            if obj_.confidence == 100:
                count_100 += 1
                if int(obj_.predicted_page_temp) <= prev_100:
                    count_unseq += 1
                else:
                    prev_100 = int(obj_.predicted_page_temp)

        if count_100 > 1:
            perc_100 = int((count_100 / len(self.object_list)) * 100)
            unseq_perc = 0
            # Updated 9/14/2020 added 'and perc_100 > 0
            if count_unseq > 0 and perc_100 > 0:
                unseq_perc = int((count_unseq / perc_100) * 100)
            if perc_100 > 50 and unseq_perc <= 5:
                start_100 = -1
                end_100 = -1
                for i in range(0, len(self.object_list)):
                    obj_ = self.object_list[i]
                    if obj_.confidence == 100:
                        if end_100 == -1:
                            start_100 = i
                        elif start_100 != -1:
                            end_100 = i
                            # do cleanup
                            if end_100 - start_100 > 1:
                                pg_start = int(self.object_list[start_100].predicted_page_temp)
                                pg_end = int(self.object_list[end_100].predicted_page_temp)
                                for j in range(start_100 + 1, end_100):
                                    if NumberHelper.is_numeric(self.object_list[j].predicted_page_temp):
                                        pg = int(self.object_list[j].predicted_page_temp)
                                        if pg < pg_start or pg > pg_end:
                                            self.object_list[j].predicted_page_temp = ""
                                # reset
                                start_100 = -1
                                end_100 = -1
                    else:
                        if start_100 != -1:
                            end_100 = i
            # update blanks in sequence from last
            last_printed = ""
            for x in range(1, len(self.object_list)):
                if self.object_list[x].predicted_page_temp == "" and NumberHelper.is_numeric(last_printed):
                    next_printed = int(last_printed) + 1
                    self.object_list[x].predicted_page_temp = str(next_printed)
                last_printed = self.object_list[x].predicted_page_temp

    # This will fill up sequencial numbers in case, all pages don't have page numbers at all
    def __perform_fillup_no_page_numbers(self):
        for object in self.object_list:
            if object.predicted_page_temp != "":
                break
        else:
            for o in self.object_list:
                o.predicted_page_temp = str(o.leaf_number)

    # filter dictionary that are not empty
    def get_dictionary_not_empty(self, dic_list: {}):
        for key in dic_list:
            if dic_list[key] != '':
                yield key

    # get object by leaf number
    def get_object_object_by_leafnumber(self, leaf_no):
        for object_ in self.object_list:
            if object_.leaf_number == leaf_no:
                return object_

        return None

    def __perform_zero_confidence_fix(self):
        for object_ in self.object_list:
            if object_.confidence != 0:
                break
        else:
            last_seq_match_count = 1
            for i in range(0, len(self.object_list)):
                if NumberHelper.is_numeric(self.object_list[i].predicted_page_temp):
                    start_num = int(self.object_list[i].predicted_page_temp)
                    expected_next_num = start_num + 1
                    seq_match_count = 0
                    for j in range(i + 1, len(self.object_list)):
                        if NumberHelper.is_numeric(self.object_list[j].predicted_page_temp):
                            next_num = int(self.object_list[j].predicted_page_temp)
                            if next_num == expected_next_num:
                                seq_match_count += 1
                        expected_next_num += 1
                    date_indicator = 1800
                    is_date = False
                    if i == 0:
                        if start_num > date_indicator:
                            is_date = True
                    else:
                        if start_num > date_indicator:
                            if NumberHelper.is_numeric(self.object_list[i - 1].predicted_page_temp):
                                if int(self.object_list[i - 1].predicted_page_temp) < date_indicator:
                                    is_date = True

                    if seq_match_count <= int(last_seq_match_count / 2) \
                            or (seq_match_count <= last_seq_match_count and len(self.object_list) <= 35) \
                            or seq_match_count == 0 or is_date:
                        old_num = self.object_list[i].predicted_page_temp
                        self.object_list[i].predicted_page_temp = ""
                        if i > 0:
                            if NumberHelper.is_numeric(self.object_list[i - 1].predicted_page_temp):
                                self.object_list[i].predicted_page_temp = str(
                                    int(self.object_list[i - 1].predicted_page_temp) + 1)
                                seq_match_count = last_seq_match_count - 1
                                # if old_num != self.object_list[i].predicted_page_temp:
                                #    self.update_0506 = True

                    last_seq_match_count = seq_match_count
                    if last_seq_match_count == 0:
                        last_seq_match_count = 1
                else:
                    if i > 0:
                        if NumberHelper.is_numeric(self.object_list[i - 1].predicted_page_temp):
                            self.object_list[i].predicted_page_temp = str(
                                int(self.object_list[i - 1].predicted_page_temp) + 1)

    def __perform_nonzero_confidence_fix(self):
        if len(self.object_list) > 5:
            if self.object_list[0].confidence == 0 and self.object_list[1].confidence == 100:
                expected_num = int(self.object_list[1].predicted_page_temp) - 1
                if expected_num > 0:
                    # self.update_0506 = True
                    self.object_list[0].predicted_page_temp = str(expected_num)

    def generate_json(self, item, json_filename, scan_data: ScanData):
        json_pages = []
        check_leaf = []  # This is blank in between numbers and non-sequence numbers.
        low_confidence_count = 0
        has_100 = False
        for object_ in self.object_list:
            if object_.confidence == 100:
                has_100 = True
            if object_.confidence == 0:
                low_confidence_count += 1
            json_pages.append(
                json.loads(json.dumps({"leafNum": object_.leaf_number,
                                       "ocr_value": object_.texts(),
                                       "confidence": object_.confidence,
                                       "pageNumber": object_.predicted_page_temp})))
            if NumberHelper.is_numeric(object_.predicted_page_temp):
                confidence = object_.confidence
                next_confidence = confidence
                if object_.leaf_number < len(self.object_list):
                    next_confidence = self.object_list[object_.leaf_number].confidence
                if confidence != next_confidence:
                    check_leaf.append(object_.leaf_number)

        # search for unsequence numbers
        for i in range(0, len(self.object_list)):
            if NumberHelper.is_numeric(self.object_list[i].predicted_page_temp):
                page_num = self.object_list[i].predicted_page_temp
                for j in range(0, len(self.object_list)):
                    if NumberHelper.is_numeric(self.object_list[j].predicted_page_temp) and i != j:
                        page_num2 = self.object_list[j].predicted_page_temp
                        if page_num == page_num2:
                            if self.object_list[i].leaf_number not in check_leaf:
                                if page_num not in self.object_list[i].texts():
                                    check_leaf.append(self.object_list[i].leaf_number)
                            break

        check_leaf.sort()

        mis_matched = 0
        total_scandata = 0
        scanned_mismatches = []
        for key in self.get_dictionary_not_empty(dic_list=scan_data.leaf_page_dictionary):
            cur_obj = self.get_object_object_by_leafnumber(int(key))
            output_val = "" if cur_obj is None else cur_obj.predicted_page_temp
            ocr_value = "" if cur_obj is None else ','.join([str(txt) for txt in cur_obj.texts()])

            if scan_data.leaf_page_dictionary[key] == output_val:
                mis_matched += 1
            else:
                scanned_mismatches.append(json.loads(json.dumps(
                    {
                        "leafNum": key,
                        "scandataValue": scan_data.leaf_page_dictionary[key],
                        "jsonOutput": output_val,
                        "ocrExtractedValue": ocr_value
                        # "ocrExtractedValue": ','.join([str(txt) for txt in self.object_list[int(key)-1].texts()])
                    })))
            total_scandata += 1

        accuracy = 0
        # if there are mismatches against the scanned_data, use it as accuracy computation
        if len(self.object_list) > 0 and has_100:
            for obj in self.object_list:
                accuracy = accuracy + obj.confidence
            accuracy = accuracy / len(self.object_list)

        json_data = {
            "identifier": item,
            "confidence": accuracy,
            "pages": json_pages
        }
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=4)

        print("Successfully saved as [" + json_filename + "] with accuracy of " + str(accuracy) + "%.")

    def __perform_granular_confidence(self):
        zero_confidence_dictionary = {}
        zero_start = -1
        zero_end = -1
        for i in range(0, len(self.object_list)):
            obj = self.object_list[i]
            if obj.confidence == 0:
                zero_end = i
                if zero_start == -1 and NumberHelper.is_numeric(obj.predicted_page_temp):
                    zero_start = i
            else:
                if zero_end >= zero_start:
                    zero_confidence_dictionary[zero_start] = zero_end
                zero_end = -1
                zero_start = -1
        # if zero_start >= 0: #exclude back matter
        #    zero_confidence_dictionary[zero_start] = zero_end
        for key in zero_confidence_dictionary:
            min_page = 0
            max_page = 0
            if key > 0:
                if NumberHelper.is_numeric(self.object_list[key - 1].predicted_page_temp):
                    min_page = int(self.object_list[key - 1].predicted_page_temp) + 1
            if zero_confidence_dictionary[key] < len(self.object_list) - 1:
                if NumberHelper.is_numeric(self.object_list[zero_confidence_dictionary[key] + 1].predicted_page_temp):
                    max_page = int(self.object_list[zero_confidence_dictionary[key] + 1].predicted_page_temp) - 1
                    if key == 0:
                        min_page = 1
            # continue here if page range is acceptable
            if min_page > 1:
                if (max_page+1)-(min_page-1) == 1:
                    for i in range(key, zero_confidence_dictionary[key]+1):
                        obj = self.object_list[i]
                        obj.confidence = 90
                elif max_page-min_page == zero_confidence_dictionary[key]-key:
                    for i in range(key, zero_confidence_dictionary[key]+1):
                        obj = self.object_list[i]
                        obj.confidence = 95
                elif max_page >= min_page+1:
                    ctr = 0
                    pages = zero_confidence_dictionary[key] - key
                    for i in range(key, zero_confidence_dictionary[key]):
                        ctr +=1
                        obj = self.object_list[i]
                        new_confidence = 0
                        if obj.predicted_page_temp in obj.texts():
                            new_confidence += 10
                            if int(obj.predicted_page_temp) <= min_page+ctr and \
                                    max_page-int(obj.predicted_page_temp) <= pages-ctr+1:
                                new_confidence += 15
                            forward_count = self.__get_matching_count_forward(i, obj.predicted_page_temp,
                                                                              zero_confidence_dictionary[key])
                            backward_count = self.__get_matching_count_backward(i, obj.predicted_page_temp, key)
                            sequence_count = forward_count + backward_count + 1
                            if sequence_count == 3:
                                new_confidence += 25
                            elif sequence_count >= 4:
                                new_confidence += 50
                        obj.confidence = new_confidence

            # get in between non-100s
            self.__perform_granular_confidence_75(key, zero_confidence_dictionary[key])

            # forward fixing of confidence
            for i in range(key + 1, zero_confidence_dictionary[key] + 1):
                if self.object_list[i - 1].confidence > self.object_list[i].confidence > 0:
                    if self.object_list[i - 1].confidence != 100:
                        self.object_list[i].confidence = self.object_list[i - 1].confidence

            # backward fixing of confidence
            for i in range(zero_confidence_dictionary[key] - 1, key - 1, -1):
                if self.object_list[i + 1].confidence > self.object_list[i].confidence > 0:
                    if self.object_list[i + 1].confidence != 100:
                        self.object_list[i].confidence = self.object_list[i + 1].confidence

            # the numbers in between completes the sequence
            self.__perform_only_missing_detection(key, zero_confidence_dictionary[key], min_page, max_page)

    def __perform_only_missing_detection(self, min, max, min_page, max_page):
        all_in_sequence = True
        expected_page = min_page
        for i in range(min, max+1):
            if self.object_list[i].confidence >= 90:
                all_in_sequence = False
                break
            elif self.object_list[i].confidence != 0:
                if int(self.object_list[i].predicted_page_temp) == expected_page:
                    expected_page += 1
                else:
                    all_in_sequence = False
                    break
        if all_in_sequence and expected_page == max_page+1:
            for i in range(min, max+1):
                if self.object_list[i].confidence == 0:
                    self.object_list[i].confidence = 90
                elif self.object_list[i].confidence != 100:
                    self.object_list[i].confidence = 99

    def __perform_granular_confidence_75(self, min_idx, max_idx):
        zero_confidence_dictionary = {}
        zero_start = -1
        zero_end = -1
        for i in range(min_idx, max_idx+1):
            obj = self.object_list[i]
            if obj.confidence == 0:
                zero_end = i
                if zero_start == -1 and NumberHelper.is_numeric(obj.predicted_page_temp):
                    zero_start = i
            else:
                if zero_start != -1 and zero_end >= zero_start:
                    zero_confidence_dictionary[zero_start] = zero_end
                zero_end = -1
                zero_start = -1
        if zero_start >= 0 and zero_end >= 0:
            zero_confidence_dictionary[zero_start] = zero_end
        for key in zero_confidence_dictionary:
            if key >= 1:
                min_page = self.object_list[key].predicted_page_temp
                max_page = self.object_list[zero_confidence_dictionary[key]].predicted_page_temp
                prev_confidence = self.object_list[key-1].confidence
                next_confidence = self.object_list[zero_confidence_dictionary[key]+1].confidence
                page_count = (zero_confidence_dictionary[key]+1) - key
                if NumberHelper.is_numeric(self.object_list[key-1].predicted_page_temp):
                    diff_page = int(self.object_list[zero_confidence_dictionary[key]+1].predicted_page_temp) - \
                                int(self.object_list[key-1].predicted_page_temp)
                    if diff_page-1 == page_count:
                        new_confidence = int((prev_confidence + next_confidence) / 2)
                        if new_confidence >= 50:
                            new_confidence = 75
                        elif new_confidence > 25:
                            new_confidence = 50
                        for i in range(key-1, zero_confidence_dictionary[key]+1):
                            if self.object_list[i].confidence < new_confidence:
                                self.object_list[i].confidence = new_confidence

    def __get_matching_count_forward(self, leaf_number, page_number, max_leaf):
        result = 0
        if NumberHelper.is_numeric(page_number):
            expected_page_number = int(page_number)+1
            for i in range(leaf_number+1, max_leaf):
                if str(expected_page_number) in self.object_list[i].texts():
                    result += 1
                expected_page_number = expected_page_number + 1
        return result

    def __get_matching_count_backward(self, leaf_number, page_number, min_leaf):
        result = 0

        if NumberHelper.is_numeric(page_number):
            expected_page_number = int(page_number) - 1
            for i in range(leaf_number-1, min_leaf, -1):
                if str(expected_page_number) in self.object_list[i].texts():
                    result += 1
                expected_page_number = expected_page_number - 1
        return result
