import os
import sys
import argparse
from book.book import Book
from book.scan_data import ScanData


def main(item: str, **kwargs):
    # determine if application is a script file or frozen exe
    application_path = ""
    xml_file_name = kwargs.get('xml_filename', "")
    xml_file_name_scan_data = kwargs.get('xml_filename_scandata', "")
    json_file_name = kwargs.get('json_filename', "")
    ia_path = kwargs.get('ia_path', "")

    if item is None and ia_path is None:
        print("Error: Unrecognized Arguments")
        return

    if item is not None and \
            (xml_file_name is not None or xml_file_name_scan_data
             is not None or json_file_name is not None or ia_path is not None):
        print("Error: \"-item\" parameter should not be mixed with other parameters")
        return

    if item is not None:
        if getattr(sys, 'frozen', False):
            application_path = os.path.dirname(sys.executable)
        elif __file__:
            application_path = os.path.dirname(__file__)

        ia_path = os.path.join(application_path, "iaitems")

        if not os.path.exists(ia_path):
            os.mkdir(ia_path)

        xml_file_name = os.path.join(application_path, "iaitems", item, "".join([item, "_djvu", ".xml"]))
        xml_file_name_scan_data = os.path.join(application_path, "iaitems", item, "".join([item, "_scandata", ".xml"]))
        json_file_name = os.path.join(application_path, "iaitems", item, "".join([item, "_pages", ".json"]))
    else:
        xml_file_name = kwargs.get('xml_filename', None)
        xml_file_name_scan_data = kwargs.get('xml_filename_scandata', None)
        json_file_name = kwargs.get('json_filename', None)
        val_error = []
        if ia_path is None:
            val_error.append("is not provided")

        if xml_file_name is None:
            val_error.append("xml_filename is not provided")

        if json_file_name is None:
            val_error.append("json_filename is not provided")

        if ','.join(val_error) != "":
            print("Error: " + '\r\n'.join(val_error))
            return

        if not os.path.isdir(ia_path):
            print("Error: ia_path \"" + ia_path + "\" does not exist")
            return

        item = xml_file_name.lower().replace("_djvu.xml", "")
        # xml_file_name = os.path.join(ia_path, item, xml_file_name)
        xml_file_name = os.path.join(ia_path, xml_file_name)
        json_file_name = os.path.join(ia_path, json_file_name)
        # json_file_name = os.path.join(ia_path, item, json_file_name)
        if not os.path.isfile(xml_file_name):
            print("Error: xml_filename \"" + xml_file_name + "\" does not exist")
            return

        if xml_file_name_scan_data is not None and xml_file_name_scan_data != "":
            # item = xml_file_name.lower().replace("_scandata.xml", "")
            xml_file_name_scan_data = os.path.join(ia_path, xml_file_name_scan_data)
            # xml_filename_scan_data = os.path.join(ia_path, item, xml_filename_scan_data)
            if not os.path.isfile(xml_file_name_scan_data):
                print("Error: xml_filename_scandata \"" + xml_file_name_scan_data + "\" does not exist")
                return

    if not os.path.isfile(xml_file_name):
        from internetarchive import download
        print("Downloading " + item + "_djvu.xml from internet archive website...")
        download(item, verbose=True, destdir=ia_path, glob_pattern='*_djvu.xml')

        print("Downloading " + item + "_scandata.xml from internet archive website...")
        try:
            download(item, verbose=True, destdir=ia_path, glob_pattern='*_scandata.xml')
        except NameError:
            pass

    # Do auto printed page generation
    if os.path.isfile(xml_file_name):
        print("Generating printed pages...")
        bk = Book(xml_file_name)
        scan_data = ScanData("")
        if xml_file_name_scan_data is not None:
            if os.path.isfile(xml_file_name_scan_data):
                scan_data = ScanData(xml_file_name_scan_data)

        bk.generate_json(item, json_file_name, scan_data=scan_data)
    else:
        print("Error: File not found [" + xml_file_name + "]!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-item", help="item name", required=False)
    parser.add_argument('-ia_path', help="IA local path", required=False)
    parser.add_argument('-xml_filename', help="item item", required=False)
    parser.add_argument('-xml_filename_scandata', help="input scandata", required=False)
    parser.add_argument('-json_filename', help="json output", required=False)
    args = parser.parse_args()
    # item = "dieivaprilisinfe00cath"
    item = args.item
    ia_path = args.ia_path
    xml_filename = args.xml_filename
    xml_filename_scandata = args.xml_filename_scandata
    json_filename = args.json_filename
    main(item, ia_path=ia_path, xml_filename=xml_filename, xml_filename_scandata=xml_filename_scandata,
         json_filename=json_filename)
