import argparse
import json
import os
import tablib
import yaml

from fastkml import kml
from operator import itemgetter
from shapely.geometry import Point

WORKING_DIR = os.getcwd()
SOT = "source_of_truth"
REQUIRED_COLUMNS = ['Name', 'Elevation', 'Latitude', 'Longitude']


def main():
    """Main function."""
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--cascade', action='store_true',
                        default=False, help='Generate full list')
    parser.add_argument('-c', '--csv', action='store_true',
                        default=False, help='produce CSV list')
    parser.add_argument('-x', '--xls', action='store_true',
                        default=False, help='produce XLS list')
    parser.add_argument('-k', '--kml', action='store_true',
                        default=False, help='produce KML map')
    parser.add_argument('-r', '--ascendingsort', action='store_true',
                        default=False, help='sort list by ascending')
    parser.add_argument('-f', '--file', action='store', dest='sotfile',
                        default=None,
                        help='single yaml file from source_of_truth'
                        ' dir to process. ex: "blah.yml"')

    # parser.add_argument('-o', '--sortby', action="store",
    #                    dest="sortby", default="Elevation")

    parsed = parser.parse_args()

    # Did the user pass in a file? use that
    if parsed.sotfile:
        truth_files = [created_full_path(parsed.sotfile)]
    # Otherwise, gather everyone!
    else:
        truth_files = collect_truth_files()

    for truth_file in truth_files:
        print("Loading {}".format(truth_file))
        hiking_list = load_yaml(truth_file, first=True,
                                cascading=parsed.cascade, explored_files=[])
        if not hiking_list:
            continue
        hiking_list.ascendingsort = parsed.ascendingsort
        hiking_list.generate_tablib_structure()
        if parsed.csv:
            hiking_list.write_csv()
        if parsed.xls:
            hiking_list.write_xls()
        if parsed.kml:
            hiking_list.write_kml()

def collect_truth_files():
    """Collect all truth files and return with full path name."""
    truth_files = list()
    for truth_file in os.listdir("source_of_truth"):
        if truth_file.endswith(".yml"):
            truth_files.append("{}/{}/{}".format(WORKING_DIR, SOT, truth_file))
    return truth_files


def created_full_path(sot_file):
    fullpath = '{}/source_of_truth/{}'.format(WORKING_DIR, sot_file)
    if not os.path.isfile(fullpath):
        raise Exception("{} does not exist".format(fullpath))
    return fullpath


def load_yaml(truth_file, first=False, cascading=True, explored_files=[]):
    """
    Loads data from file yaml SOT passed in and returns a HikingList object.
    This function is designed to be recursive.
    """
    # anti loop mechanism
    explored_files.append(truth_file)
    with open(truth_file, 'r') as tf:
        # Read our YML truth file.
        read_hiking_list = tf.read()
        hiking_list = yaml.load(read_hiking_list)
        # Grab filename from YAML file or fall back to Truth File name.
        filename = hiking_list.get('list_name', truth_file.split('/')[-1][:-4])
        # Gather data/metadata and defaults.
        peaks = hiking_list.get('peaks', [])
        maximum = hiking_list.get('max', 0)
        sortby = hiking_list.get('sortby', 'Elevation')
        standalone = hiking_list.get('standalone', True)
        location = hiking_list.get('location', 'Unspecified')
        imported_resources = hiking_list.get('import', [])
        forced_imported_resources = hiking_list.get('forced_import', [])
        if not isinstance(imported_resources, list):
            raise Exception("Imported Resource "
                            "must be list! {}".format(truth_file))
        ordered_columns = hiking_list.get('ordered_columns',
                                          REQUIRED_COLUMNS.copy())
        if not all(item in ordered_columns for item in REQUIRED_COLUMNS):
            raise Exception("Manditory columns missing from ordered_columns "
                            "in {}. Required: {} Have: {}".format(
                                truth_file, REQUIRED_COLUMNS, ordered_columns))
        explicit_columns = hiking_list.get('only_use_explicit_ordered_columns',
                                           False)
        if explicit_columns and not hiking_list.get('ordered_columns', None):
            raise('Can only use "only_use_explicit_ordered_columns" when'
                  ' ordered_columns is specified! in {}'.format(truth_file))
        # peakcount workaround.
        peakcountlist = list()

        # If this yaml file is loaded first and standalone is turned off and
        # cascading is turned off, then return an empty list.
        if first and not standalone:
            return None
        # Do we import something and have cascading? Then load 'em up.
        if imported_resources and cascading:
            for imported_resource in imported_resources:
                imported_list = generate_import(imported_resource)
                # if the imported list was already explored
                # then we have an import loop! fuck! Throw error and Bail!
                if imported_list in explored_files:
                    raise Exception("Import Cycle {} located in "
                                    "{}".format(explored_files, truth_file))
                imported_list_peaks = load_yaml(imported_list,
                                                explored_files=explored_files)
                peaks = peaks + imported_list_peaks
        # if cascading is off but the SOT file forces explicit imports do this:
        if forced_imported_resources and not cascading:
            for forced_imported_resource in forced_imported_resources:
                imported_list = generate_import(forced_imported_resource)
                imported_list_peaks = load_yaml(imported_list, cascading=False)
                peaks = peaks + imported_list_peaks
        # if we've got no cascading, and we've got a max limit set, we need to
        # load all the imports and conjure up a length.
        if first and not cascading and maximum:
            for imported_resource in imported_resources:
                imported_list = generate_import(imported_resource)
                # if the imported list was already explored
                # then we have an import loop! fuck! Throw error and Bail!
                if imported_list in explored_files:
                    raise Exception("Import Cycle {} located in "
                                    "{}".format(explored_files, truth_file))
                imported_list_peaks = load_yaml(imported_list,
                                                explored_files=explored_files)
                peakcountlist = peakcountlist + imported_list_peaks

        # Make sure our manditory columns are present for every peak.
        validate_columns(peaks, truth_file)
        if first:
            return HikingList(peaks, location,
                              filename, standalone, cascading,
                              maximum=maximum, sortby=sortby,
                              explicit_columns=explicit_columns,
                              ordered_columns=ordered_columns,
                              peakcountlist=peakcountlist)
        # end of recursion, remove truth_file from explored list. Tree
        # redundancy is taken care of in the HikingList Object by
        # self.remove_duplicate_peaks()
        explored_files.remove(truth_file)
        return peaks


def import_recursion(imported_resources):
    for imported_resource in imported_resources:
        imported_list = generate_import(imported_resource)
        # if the imported list was already explored
        # then we have an import loop! fuck! Throw error and Bail!
        if imported_list in explored_files:
            raise Exception("Import Cycle {} located in "
                            "{}".format(explored_files, truth_file))
        imported_list_peaks = load_yaml(imported_list,
                                        explored_files=explored_files)
        return imported_list_peaks


def generate_import(imported_resource):
    """Produces full path yml file import."""
    return '{}/{}/{}'.format(WORKING_DIR, SOT, imported_resource)

def validate_columns(peaks, src_file):
    """
    Validates the manditory columns exist for every peak, raises exception
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
    def __init__(self, peaks, location, filename, standalone, cascading,
                 ordered_columns=[], maximum=0, sortby='Elevation',
                 explicit_columns=False, peakcountlist=[]):
        self.peaks = peaks
        self.maximum = maximum
        self.location = location
        self.cascading = cascading
        self.standalone = standalone
        self.filename = filename
        self.ordered_columns = ordered_columns
        self.sortby = sortby
        self.explicit_columns = explicit_columns
        self.ascendingsort = False
        self.peakcountlist = peakcountlist

    @property
    def output_dir(self):
        """
        Output directory for any lists files created %CWD/lists/%location.
        """
        if self.cascading:
            subdir = "full"
        else:
            subdir = "abridged"
        return '{}/lists/{}/{}/{}'.format(WORKING_DIR, self.location,
                                             self.filename, subdir)

    @property
    def output_file(self):
        """Output file without type complete with full path."""
        return '{}/{}'.format(self.output_dir, self.filename)

    def generate_tablib_structure(self):
        """Generate tablib structure from provided object data."""
        # Collect any non-default columns.
        self.collect_extra_columns()
        # Validate sortby choice actually exists.
        self.validate_sortby_column_exists()
        # remove duplicate peaks from self.peaks
        self.remove_duplicate_peaks()
        # sort the peaks list
        self.sort_by()
        # test
        self.calculate_abridge_peak_list_length()
        # trim the peaks list
        self.trim_by_maximum()
        # validate columns, compare against what was passed in.
        self.format_data_structure()
        print(self.tablib_data)

    def calculate_abridge_peak_list_length(self):
        """
        Changes the maximum to work with abridged lists
        This is achieved by first calculating the total number of unique
        imported peaks as a set of the entire peak set. Then subtracting that
        from the set maximum to find the accurate difference for the abridged
        set.
        """
        if self.maximum and self.peakcountlist:
            uniqueImportedPeaks = [dict(t) for t in set(
                                  [tuple(d.items()) for d in self.peakcountlist])]
            uniqueProperPeaks = [dict(t) for t in set(
                                [tuple(d.items()) for d in self.peaks])]
            uniqueAllPeaks = [dict(t) for t in set(
                             [tuple(d.items()) for d in uniqueProperPeaks + uniqueImportedPeaks])]
            importLth = len(uniqueAllPeaks) - len(uniqueProperPeaks)
            abridgedLth = self.maximum - importLth
            self.maximum = abridgedLth

    def remove_duplicate_peaks(self):
        """Remove all duplicate peak entries. Does not preserve ordering."""
        self.peaks = [dict(t) for t in set(
                     [tuple(d.items()) for d in self.peaks])]

    def collect_extra_columns(self):
        """Return a list of required columns and any extra columns."""
        # if we're only using columns explicitly passed in, bail.
        if self.explicit_columns:
            return
        # Otherwise, add them as we find them.
        for peak in self.peaks:
            for column in peak.keys():
                if column not in self.ordered_columns:
                    self.ordered_columns.append(column)

    def validate_sortby_column_exists(self):
        """ Throws exception if sortby column doesn't exist. """
        if self.sortby not in self.ordered_columns:
            raise Exception("Sortby column not valid column! Have: {} Want: {}"
                            "".format(self.ordered_columns, self.sortby))

    def trim_by_maximum(self):
        """
        Trims the peaks list down to the maximum size. This should only be
        called after the list is sorted. max of 0 is interpreted as infinity.
        """
        if self.maximum:
            self.peaks = self.peaks[:int(self.maximum)]

    def sort_by(self):
        """
        Return list of peaks sorted by requested field in requested order.
        """
        self.peaks = sorted(self.peaks, key=itemgetter("Name"),
                            reverse=not self.ascendingsort)
        self.peaks = sorted(self.peaks, key=itemgetter(self.sortby),
                            reverse=not self.ascendingsort)

    def format_data_structure(self):
        """Parse data for presentation to tablib, a format agnostic dataset."""
        tablib_data = list()
        for peak in self.peaks:
            columnized_data = list()
            for ordered_column_name in self.ordered_columns:
                columnized_data.append(peak.get(ordered_column_name, ""))
            tablib_data.append(columnized_data)
        self.tablib_data = tablib.Dataset(*tablib_data,
                                          headers=self.ordered_columns,
                                          title=self.filename)

    def write_csv(self):
        """Write CSV file."""
        filetype = 'csv'
        make_dir_if_not_exist(self.output_dir)
        with open('{}.csv'.format(self.output_file), 'w') as output_csv:
            output_csv.write(self.tablib_data.export(filetype))

    def write_xls(self):
        """Write XLS file."""
        filetype = 'xls'
        make_dir_if_not_exist(self.output_dir)
        with open('{}.xls'.format(self.output_file), 'wb') as output_xls:
            output_xls.write(self.tablib_data.export(filetype))

    def write_kml(self):
        """Write KML file."""
        filetype = 'kml'
        make_dir_if_not_exist(self.output_dir)
        # shamefully dump as JSON then unmarshal into a dict -- sigh.
        peak_dict = json.loads(self.tablib_data.export('json'))

        k = kml.KML()
        ns = '{http://www.opengis.net/kml/2.2}'

        # Create a KML Document and add it to the KML root object
        d = kml.Document(ns,
                         self.filename,
                         self.filename,
                         'pinmap for {}'.format(self.filename))
        k.append(d)
        kmlFolder = kml.Folder(ns,
                                    self.filename,
                                    self.filename,
                                    'kml map of list points for {}'.format(self.filename))
        for peak in peak_dict:
            details = ''
            for key, val in sorted(peak.items()):
                details += '{}: {}\n'.format(key, val)
            p = kml.Placemark(ns, peak['Name'], peak['Name'], details)
            p.geometry = Point(peak['Longitude'], peak['Latitude'])
            kmlFolder.append(p)
        d.append(kmlFolder)
        with open('{}.kml'.format(self.output_file), 'w') as output_kml:
            output_kml.write(k.to_string(prettyprint=True))



if __name__ == "__main__":
    main()
