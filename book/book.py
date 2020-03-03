import xml.etree.ElementTree as ET
import json

from .object import Object
from .number_helper import NumberHelper
from .scan_data import ScanData


class Book:
    def __init__(self, xml_filename):
        tree = ET.parse(xml_filename)
        root = tree.getroot()
        self.object_list = []
        self.blank_gap_dictionary = {}
        self.last_blank_start = 0
        expected_leaf_no = 1
        for object_element in root.iter('OBJECT'):
            object_ = Object(object_element)
            object_.extract_words()
            object_.extract_possible_page_numbers()
            # Start: added 2/14
            if object_.leaf_number != expected_leaf_no:
                for i in range(expected_leaf_no, object_.leaf_number):
                    t_object = Object("")
                    t_object.leaf_number = i
                    self.object_list.append(t_object)
            # End: added 2/14
            self.object_list.append(object_)
            expected_leaf_no = object_.leaf_number + 1
        #do prediction based on previous, current, and next page
        self.__perform_temporary_prediction()
        #do fill-up gaps
        self.__perform_fillup_gaps_arabic()
        #generate confidence +10 and -10 sequence
        self.__build_page_confidence()
        self.__perform_fillup_gaps_0_confidence()
        #updating roman numerals pages
        self.__perform_fillup_roman_numerals()
        #fill up blank possible numeric values, from start, from end and between
        self.__perform_fillup_numeric_blanks()
        #fix 0 confidence in between that will match actual gaps
        self.__perform_fillup_gaps_0_confidence()
        self.__perform_fillup_numeric_blanks()
        #rebuild confidence
        self.__build_page_confidence()
        #in a case no page numbers predicted at all, use the leaf number
        self.__perform_fillup_no_page_numbers()
        #self.__print_pages("After final prediction!")

    #temporary routine to print details in the console
    def __print_pages(self, caption):
        print(caption)
        for obj in self.object_list:
            p = ""
            c = ""
            if obj.predicted_page_temp is not None:
                p = obj.predicted_page_temp
            if obj.candidate_printed_page is not None:
                c = obj.candidate_printed_page
            print(obj.leaf_number, p, obj.confidence, obj.texts())

    # Perform temporary prediction, filling up objects (predicted_page_temp and
    # expected_next_printed_page).
    def __perform_temporary_prediction(self):
        blank_start = -1
        blank_end = -1
        all_blanks = True
        for i in range(0, len(self.object_list)-1):
            self.object_list[i].predict_page_printed_number(self.object_list)
            if not self.object_list[i].predicted_page_temp:
                if blank_start == -1:
                    blank_start = i
                blank_end = i
            else:
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
        for i in range(0,len(self.object_list)-2):
            gap = 1
            if self.object_list[i].predicted_page_temp == "":
                for j in range(i+1, len(self.object_list)-2):
                    for text in self.object_list[i].texts():
                        if text.isnumeric():
                            expected_next_printed_page = str(int(text) + gap)
                            if self.object_list[i].is_next_page_matched(self.object_list[j], expected_next_printed_page):
                                self.object_list[i].predicted_page_temp = text
                                self.object_list[j].predicted_page_temp = expected_next_printed_page
                                break
                    gap += 1
                    if gap > 10:
                        break
        blank_start = -1
        blank_end = -1
        self.blank_gap_dictionary.clear()
        for i in range(0, len(self.object_list)-1):
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
                if start_candidate.isnumeric() and end_candidate.isnumeric():
                    if str(int(start_candidate)-1) == self.object_list[blank_start-1].predicted_page_temp \
                            and str(int(end_candidate)+1) == self.object_list[blank_end+1].predicted_page_temp:
                        for i in range(blank_start, blank_end + 1):
                            self.object_list[i].predicted_page_temp = self.object_list[i].candidate_printed_page
                            self.object_list[i].sure_prediction = True
                        matched_keys.append(key)

        # Remove successfully matched
        for key in matched_keys:
            self.blank_gap_dictionary.pop(key)

    #building confidence
    def __build_page_confidence(self):
        #forward
        for obj in self.object_list:
            if obj.confidence == 0:
                obj.confidence = self.__get_confidence_forward(obj.leaf_number, obj.predicted_page_temp, 10)
        #backward
        for i in range(len(self.object_list)-1, 0, -1):
            if self.object_list[i].confidence == 0:
                self.object_list[i].confidence = self.__get_confidence_backward(self.object_list[i].leaf_number,
                                                                                self.object_list[i].predicted_page_temp,
                                                                                10)

    #set the leaf number to 100% confidence if it can match to the next max_match
    def __get_confidence_forward(self, leaf_number, page_number, max_match):
        result = 0
        if (page_number.isnumeric()):
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

    #set the leaf number to 100% confidence if it can match to the previous max_match
    def __get_confidence_backward(self, leaf_number, page_number, max_match):
        result = 0

        if (page_number.isnumeric()):
            match_counter = 0
            expected_page_number = int(page_number) - 1
            for i in range(leaf_number-2, 0, -1):
                if self.object_list[i].predicted_page_temp == str(expected_page_number):
                    match_counter = match_counter + 1
                expected_page_number = expected_page_number - 1
                if match_counter >= max_match:
                    result = 100
                    break
                if i < leaf_number - (max_match * 2):
                    break
        return result

    def __perform_fillup_gaps_0_confidence(self):
        blank_start = -1
        blank_end = 0

        for i in range(0, len(self.object_list)-1):
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
                        printed_start = int(self.object_list[blank_start-1].predicted_page_temp)
                    printed_end = int(self.object_list[blank_end+1].predicted_page_temp)
                    if ((printed_end - printed_start)-2) == (blank_end - blank_start):
                        page_number = printed_start + 1
                        for j in range(blank_start, blank_end + 1):
                            self.object_list[j].predicted_page_temp = str(page_number)
                            self.object_list[j].confidence = 100
                            page_number = page_number + 1
                    else:
                        #should solve 101,102,blank,blank,103,104,blank,blank,105,106
                        for j in range(blank_start, blank_end + 1):
                            if self.object_list[j].predicted_page_temp.isnumeric():
                                if (int(self.object_list[j].predicted_page_temp) > printed_start) and \
                                        (int(self.object_list[j].predicted_page_temp) < printed_end):
                                    pass
                                else:
                                    self.object_list[j].predicted_page_temp = ""
                                    self.object_list[j].confidence = 0
                    blank_start = -1
                    blank_end = 0

    #returns the index of first leaf with 100 confidence
    def __get_first_confidence_index_100(self):
        result = -1
        for i in range(0, len(self.object_list)):
            if self.object_list[i].confidence == 100:
                result = i
                break
        return result

    #returns the index of the last leaf with 100 confidence
    def __get_last_confidence_index_100(self):
        result = -1
        for i in range(len(self.object_list)-1, 0, -1):
            if self.object_list[i].confidence == 100:
                result = i
                break
        return result

    #get the lower index that the page number matches with computed value from the starting index or idx100
    def __get_lower_index(self, idx100):
        result = -1
        page_number_idx100 = int(self.object_list[idx100].predicted_page_temp)
        for i in range(idx100-1, -1, -1):
            if self.object_list[i].predicted_page_temp.isnumeric():
                page_number_lower = int(self.object_list[i].predicted_page_temp)
                if page_number_lower < page_number_idx100:
                    if self.__get_confidence_backward(self.object_list[i].leaf_number,
                                                      self.object_list[i].predicted_page_temp,
                                                      2):
                        result = i
                        break
                    if page_number_idx100 - (idx100-i) == page_number_lower:
                        result = i
                        break
        return result

    def __get_higher_index(self, idx100):
        result = -1
        page_number_idx100 = int(self.object_list[idx100].predicted_page_temp)
        for i in range(idx100+1, len(self.object_list)):
            if self.object_list[i].predicted_page_temp.isnumeric():
                page_number_higher = int(self.object_list[i].predicted_page_temp)
                if page_number_higher > page_number_idx100:
                    if self.__get_confidence_forward(self.object_list[i].leaf_number,
                                                      self.object_list[i].predicted_page_temp,
                                                      2):
                        result = i
                        break
        return result

    def __perform_fillup_numeric_blanks(self):
        # first part
        page_number = 0
        while True:
            idx = self.__get_first_confidence_index_100()
            if idx > 0:
                lower_idx = self.__get_lower_index(idx)
                if lower_idx != -1:
                    self.object_list[lower_idx].confidence = 100
                else:
                    lower_idx = idx - int(self.object_list[idx].predicted_page_temp) + 1
                    if lower_idx > 0:
                        if self.object_list[lower_idx].predicted_page_temp != "1":
                            self.object_list[lower_idx].predicted_page_temp = "1"
                            self.object_list[lower_idx].confidence = 100
                    break
            else:
                break

        # last part
        page_number = 0
        while True:
            idx = self.__get_last_confidence_index_100()
            if idx != -1:
                higher_idx = self.__get_higher_index(idx)
                if higher_idx != -1:
                    self.object_list[higher_idx].confidence = 100
                else:
                    break
            else:
                break


        last_printed = ""
        for x in range(1, len(self.object_list)):
            if self.object_list[x].predicted_page_temp == "" and last_printed.isnumeric():
                next_printed = int(last_printed) + 1
                self.object_list[x].predicted_page_temp = str(next_printed)
            last_printed = self.object_list[x].predicted_page_temp

        page_number = 0
        # backwards with 0 confidence
        for x in range(len(self.object_list)-1, -1, -1):
            if self.object_list[x].confidence == 100:
                page_number = int(self.object_list[x].predicted_page_temp) + 1

                for j in range(x+1, len(self.object_list)):
                    self.object_list[j].predicted_page_temp = str(page_number)
                    self.object_list[j].confidence = 100
                    page_number += 1
                break

        #if it does not start with 1 from the top
        initial_count = 0
        for x in range(1, len(self.object_list)):
            initial_count += 1
            if self.object_list[x].predicted_page_temp.isnumeric():
                if int(self.object_list[x].predicted_page_temp) < initial_count:
                    page_number = int(self.object_list[x].predicted_page_temp) - 1
                    if page_number >= 1:
                        for j in range(x-1, -1, -1):
                            if page_number < 1:
                                self.object_list[j].confidence = 100
                                if self.object_list[j].predicted_page_temp.isnumeric() or \
                                        self.object_list[j].predicted_page_temp == "":
                                    self.object_list[j].predicted_page_temp = ""
                            else:
                                self.object_list[j].predicted_page_temp = str(page_number)
                                self.object_list[j].confidence = 100
                            page_number -= 1
                break

    def __perform_fillup_roman_numerals(self):
        blank_end = 0
        roman_count = 0
        for object_ in self.object_list:
            if not object_.predicted_page_temp:
                blank_end += 1
                for text in object_.texts():
                    if NumberHelper.is_valid_roman_numeral(text):
                        roman_count += 1
                        break
            if object_.confidence == 100:
                break

        # Make sure that there are at least 3 roman numeral appearnaces.
        if roman_count >= 3:
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
                if blank_end-page < max_matched_count:
                    break

            if max_matched_count >= 3:
                for page in range(max_matched_start, blank_end):
                    roman_prediction = NumberHelper.int_to_roman((page - max_matched_start) + 1).lower()
                    self.object_list[page].predicted_page_temp = roman_prediction

    # This will fill up sequencial numbers in case, all pages don't have page numbers at all
    def __perform_fillup_no_page_numbers(self):
        for object in self.object_list:
            if object.predicted_page_temp != "":
                break
        else:
            confidence = 0
            for o in self.object_list:
                o.predicted_page_temp = str(o.leaf_number)
                o.confidence = confidence
                if confidence == 0:
                    confidence = 100
                else:
                    confidence = 0

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

    def generate_json(self, item, json_filename, scan_data: ScanData):
        json_pages = []
        check_leaf = []         # This is blank in between numbers and non-sequence numbers.
        for object_ in self.object_list:
            json_pages.append(
                json.loads(json.dumps({"leafNum": object_.leaf_number,
                                       "ocr_value": object_.texts(),
                                       "pageNumber": object_.predicted_page_temp})))
            if object_.predicted_page_temp.isnumeric():
                confidence = object_.confidence
                next_confidence = confidence
                if object_.leaf_number < len(self.object_list):
                    next_confidence = self.object_list[object_.leaf_number].confidence
                if confidence != next_confidence:
                    check_leaf.append(object_.leaf_number)

        #search for unsequence numbers
        for i in range(0, len(self.object_list)):
            if self.object_list[i].predicted_page_temp.isnumeric():
                page_num = self.object_list[i].predicted_page_temp
                for j in range(0, len(self.object_list)):
                    if self.object_list[j].predicted_page_temp.isnumeric() and i != j:
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
        accuracy = 100.00

        # if there are mismatches against the scanned_data, use it as accuracy computation
        if len(self.object_list) > 0:
            if len(scanned_mismatches) > 0 or len(scan_data.leaf_page_dictionary) > 0:
                accuracy = (1 - (len(scanned_mismatches) / len(self.object_list))) * 100
            elif len(check_leaf) > 0:
                accuracy = (1 - (len(check_leaf) / len(self.object_list))) * 100
        else:
            accuracy = 0

        json_data = {
            "identifier": item,
            "confidence": accuracy,
            "leafForChecking": check_leaf,
            "scandataOutputMismatched": scanned_mismatches,
            "pages": json_pages
        }
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=4)

        print("Successfully saved as [" + json_filename + "] with accuracy of " + str(accuracy) + "%.")
