import argparse
import os
import tablib
import yaml

from operator import itemgetter

WORKING_DIR = os.getcwd()
SOT = "source_of_truth"
REQUIRED_COLUMNS = ['Name', 'Elevation', 'Latitude', 'Longitude']


def main():
    """Main function."""
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--cascade', action='store_true', default=False)
    parser.add_argument('-c', '--csv', action='store_true', default=False)
    parser.add_argument('-x', '--xls', action='store_true', default=False)
    parser.add_argument('-r', '--forwardsort', action='store_true', default=False)
    parser.add_argument('-o', '--sortby', action="store",
                        dest="sortby", default="Elevation")

    parsed = parser.parse_args()

    truth_files = collect_truth_files()
    for truth_file in truth_files:
        print("Loading {}".format(truth_file))
        hiking_list = load_yaml(truth_file, first=True,
                                cascading=parsed.cascade)
        hiking_list.sortby = parsed.sortby
        hiking_list.forwardsort = parsed.forwardsort
        hiking_list.generate_tablib_structure()
        if parsed.csv:
            hiking_list.write_csv()
        if parsed.xls:
            hiking_list.write_xls()


def collect_truth_files():
    """Collect all truth files and return with full path name."""
    truth_files = list()
    for truth_file in os.listdir("source_of_truth"):
        if truth_file.endswith(".yml"):
            truth_files.append("{}/{}/{}".format(WORKING_DIR, SOT, truth_file))
    return truth_files


def load_yaml(truth_file, first=False, cascading=True):
    """
    Loads data from file yaml SOT passed in and returns a HikingList object.
    This function is designed to be recursive.
    """
    with open(truth_file, 'r') as tf:
        read_hiking_list = tf.read()
        hiking_list = yaml.load(read_hiking_list)
        filename = truth_file.split('/')[-1][:-4]
        peaks = hiking_list['peaks']
        standalone = hiking_list.get('standalone', True)
        location = hiking_list.get('location', 'Unspecified')
        imported_resource = hiking_list.get('import', "")
        # If this yaml file is loaded first and standalone is turned off and
        # cascading is turned off, then return an empty list.
        if first and not standalone and not cascading:
            return [], hiking_list["location"]
        # Do we import something and have cascading? then load 'em up.'
        if imported_resource and cascading:
            imported_list = "{}/{}/{}".format(WORKING_DIR, SOT,
                                              imported_resource)
            imported_list_peaks = load_yaml(imported_list)
            peaks = peaks + imported_list_peaks
        validate_columns(peaks, truth_file)
        if first:
            return HikingList(peaks, location, filename, standalone)
        return peaks


def validate_columns(peaks, src_file):
    """
    Validates required columns exist for every peak, raises exception
    upon failure.
    """
    for peak in peaks:
        columns = peak.keys()
        for required_column in REQUIRED_COLUMNS:
            if required_column not in columns:
                raise Exception(
                 'Missing column "{}" in {} in {}'.format(required_column,
                                                          peak, src_file))


def make_dir_if_not_exist(directory):
    """If directory doesn't exist, created it."""
    if not os.path.exists(directory):
        os.makedirs(directory)


class HikingList(object):
    def __init__(self, peaks, location, filename, standalone,
                 ordered_columns=[]):
        self.peaks = peaks
        self.location = location
        self.standalone = standalone
        self.filename = filename
        self.ordered_columns = ordered_columns
        self.sortby = None
        self.forwardsort = False
        # make this a pass in option:
        self.ordered_columns = REQUIRED_COLUMNS.copy()

    @property
    def output_dir(self):
        """
        Output directory for any lists files created %CWD/lists/%location.
        """
        return '{}/lists/{}'.format(WORKING_DIR, self.location)

    @property
    def output_file(self):
        """Output file without type complete with full path."""
        return '{}/{}'.format(self.output_dir, self.filename)

    def generate_tablib_structure(self):
        """Generate tablib structure from provided object data."""
        self.collect_extra_columns()
        self.sort_by()
        # validate columns, compare against what was passed in.
        self.format_data_structure()
        print(self.tablib_data)

    def collect_extra_columns(self):
        """Return a list of required columns and any extra columns."""
        for peak in self.peaks:
            for column in peak.keys():
                if column not in self.ordered_columns:
                    self.ordered_columns.append(column)

    def sort_by(self):
        """
        Return list of peaks sorted by requested field in requested order.
        """
        self.peaks = sorted(self.peaks, key=itemgetter(self.sortby),
                            reverse=not self.forwardsort)

    def format_data_structure(self):
        """Parse data for presentation to tablib, a format agnostic dataset."""
        tablib_data = list()
        for peak in self.peaks:
            columnized_data = list()
            for ordered_column_name in self.ordered_columns:
                columnized_data.append(peak.get(ordered_column_name, ""))
            tablib_data.append(columnized_data)
        self.tablib_data = tablib.Dataset(*tablib_data,
                                          headers=self.ordered_columns)

    def write_csv(self):
        """Write CSV file."""
        make_dir_if_not_exist(self.output_dir)
        with open('{}.csv'.format(self.output_file), 'w') as output_csv:
            output_csv.write(self.tablib_data.export('csv'))

    def write_xls(self):
        """Write XLS file."""
        make_dir_if_not_exist(self.output_dir)
        with open('{}.xls'.format(self.output_file), 'wb') as output_xls:
            output_xls.write(self.tablib_data.export('xls'))


if __name__ == "__main__":
    main()
