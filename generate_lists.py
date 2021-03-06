import argparse
import json
import os
import sys
import tablib
import yaml

from fastkml import kml
from operator import itemgetter
from shapely.geometry import Point

WORKING_DIR = os.getcwd()
SOT = "source_of_truth"
REQUIRED_COLUMNS = ['Name', 'Elevation', 'Latitude', 'Longitude']
VALID_AUTOGEN_COLUMNS = ['Rank', 'Meters']

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
    parser.add_argument('-p', '--pessimism', action='store',
                        dest='pessimism',
                        default=2.5,
                        help='percentage of pessimism for lists with col rule')
    parser.add_argument('-l', '--pessimistic', action='store_true',
                        dest='pessimistic',
                        default=False,
                        help='generate threshold lists with pessimism')
    parser.add_argument('-o', '--optimism', action='store',
                        dest='optimism',
                        default=2.5,
                        help='percentage of optimism for lists with col rule')
    parser.add_argument('-j', '--optimistic', action='store_true',
                        dest='optimistic',
                        default=False,
                        help='generate threshold lists with optimism')
    parsed = parser.parse_args()

    # Did the user pass in a file? use that
    if parsed.sotfile:
        truth_files = [created_full_path(parsed.sotfile)]
    # Otherwise, gather everyone!
    else:
        truth_files = collect_truth_files()

    if parsed.optimistic and parsed.pessimistic:
        print("Bork! can't be both optimistic and pessimistic!")
        sys.exit(0)

    for truth_file in truth_files:
        print("Loading {}".format(truth_file))
        hiking_list = load_yaml(truth_file, first=True,
                                cascading=parsed.cascade, explored_files=[])
        if not hiking_list:
            continue
        hiking_list.ascendingsort = parsed.ascendingsort
        hiking_list.pessimism = int(parsed.pessimism)
        hiking_list.pessimistic = parsed.pessimistic
        hiking_list.optimism = int(parsed.optimism)
        hiking_list.optimistic = parsed.optimistic
        # are we using optimistic or pessimistic options but no
        # prominence_threshold has been supplied? bail.
        if ((hiking_list.pessimistic or hiking_list.optimistic) and
            not hiking_list.prominence_threshold):
            continue

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


def load_yaml(truth_file, first=False, cascading=True,
              explored_files=[], lookahead=True):
    """
    Loads data from file yaml SOT passed in and returns a HikingList object.
    This function is designed to be recursive.
    """
    # anti loop mechanism
    explored_files.append(truth_file)

    # peakcount workaround.
    peakcountlist = list()

    # Load up our truth file
    with open(truth_file, 'r') as tf:
        # Read our YML truth file.
        read_hiking_list = tf.read()
        hiking_list = yaml.load(read_hiking_list)
        # Grab filename from YAML file or fall back to Truth File name.
        filename = hiking_list.get('list_name', truth_file.split('/')[-1][:-4])

        # Gather "prominence_threshold" int and validate
        prominence_threshold = hiking_list.get('prominence_threshold', 0)
        validate_type("prominence_threshold Resource",
                      prominence_threshold, truth_file, int)

        # Gather "peaks" list and validate
        peaks = hiking_list.get('peaks', [])
        validate_type("peaks Resource", peaks, truth_file, list)

        # Gather "max" int and validate
        maximum = hiking_list.get('max', 0)
        validate_type("max Value", maximum, truth_file, int)

        # Gather "prominence_style" bool and validate
        prominence_style = hiking_list.get('prominence_style', False)
        validate_type("prominence_style Bool", prominence_style,
                      truth_file, int)

        # Gather "sortby" column name string and validate
        sortby = hiking_list.get('sortby', 'Elevation')
        validate_type("sortby Column", sortby, truth_file, str)

        # Gather "standalone" boolean and validate
        standalone = hiking_list.get('standalone', True)
        validate_type("standalone Bool", standalone, truth_file, bool)

        # Gather "location" string and validate
        location = hiking_list.get('location', 'Unspecified')
        validate_type("location Value", location, truth_file, str)

        # Gather "forced_import" list and validate
        forced_imported_resources = hiking_list.get('forced_import', [])
        validate_type("forced_import Resources", forced_imported_resources,
                      truth_file, list)

        # Gather "lookaheads" list and validate
        lookaheads = hiking_list.get('lookaheads', [])
        validate_type("lookahead Resources", lookaheads,
                      truth_file, list)

        # Gather "autogen_columns" list and validate
        autogen_columns = hiking_list.get('autogenerated_columns', [])
        validate_type("autogen_columns Resource", autogen_columns,
                      truth_file, list)
        validate_autogen_columns(autogen_columns)

        # Gather "import" list and validate
        imported_resources = hiking_list.get('import', [])
        validate_type("Imported Resource", imported_resources,
                      truth_file, list)

        # Gather "ordered_columns" list and validate
        ordered_columns = hiking_list.get('ordered_columns',
                                          REQUIRED_COLUMNS.copy())
        validate_type("ordered_columns Resource", ordered_columns,
                      truth_file, list)
        if not all(item in ordered_columns for item in REQUIRED_COLUMNS):
            raise Exception("Manditory columns missing from ordered_columns "
                            "in {}. Required: {} Have: {}".format(
                                truth_file, REQUIRED_COLUMNS, ordered_columns))

        # Gather "explicit_columns" list and validate
        explicit_columns = hiking_list.get('only_use_explicit_ordered_columns',
                                           False)
        validate_type("explicit_columns Bool", explicit_columns, truth_file,
                      bool)
        if explicit_columns and not hiking_list.get('ordered_columns', None):
            raise('Can only use "only_use_explicit_ordered_columns" when'
                  ' ordered_columns is specified! in {}'.format(truth_file))

        # If this yaml file is loaded first and standalone is turned off,
        # then return an empty list.
        if first and not standalone:
            return None

        # Here is the recursion loop. Where all the magic happens!
        # - If this is the first call and cascading is on, add found peaks to
        # the peak list
        # - If this is the first call and cascading is off, add found peaks to
        # the peakcount list for use in rankings on abridged lists later on.
        # - If not first and cascading is on, add found peaks to peak list
        # (for returning to original caller)
        for imported_resource in imported_resources:
            imported_list = generate_import(imported_resource)
            # if the imported list was already explored
            # then we have an import loop! fuck! Throw error and bail!

            if imported_list in explored_files:
                raise Exception("Import Cycle {} located in "
                                "{}".format(explored_files, truth_file))
            imported_list_peaks = load_yaml(imported_list,
                                            explored_files=explored_files,
                                            lookahead=False)
            if first and cascading:
                peaks = peaks + imported_list_peaks
            elif first and not cascading:
                peakcountlist = peakcountlist + imported_list_peaks
            elif cascading:
                peaks = peaks + imported_list_peaks

        # if forced imports are available and cascading is off load
        # 'em up one at a time.
        if forced_imported_resources and not cascading:
            for forced_imported_resource in forced_imported_resources:
                imported_list = generate_import(forced_imported_resource)
                imported_list_peaks = load_yaml(imported_list, cascading=False,
                                                lookahead=False)
                peaks = peaks + imported_list_peaks
        if lookaheads and lookahead:
            for forced_imported_resource in lookaheads:
                imported_list = generate_import(forced_imported_resource)
                imported_list_peaks = load_yaml(imported_list, cascading=False,
                                                lookahead=False)
                peaks = peaks + imported_list_peaks

        # IF we're back to the original caller, return a HikingList object.
        if first:
            # Make sure our manditory columns are present for every peak.
            validate_columns(peaks, truth_file)

            return HikingList(peaks, location,
                              filename, standalone, cascading,
                              maximum=maximum, sortby=sortby,
                              explicit_columns=explicit_columns,
                              ordered_columns=ordered_columns,
                              peakcountlist=peakcountlist,
                              autogen_columns=autogen_columns,
                              prominence_style=prominence_style,
                              prominence_threshold=prominence_threshold
                              )
        # end of recursion, remove truth_file from explored list. Tree
        # redundancy is taken care of in the HikingList Object by
        # self.remove_duplicate_peaks()
        if truth_file in explored_files:
            explored_files.remove(truth_file)
        return peaks


def generate_import(imported_resource):
    """Produces full path yml file import."""
    return '{}/{}/{}'.format(WORKING_DIR, SOT, imported_resource)


def make_dir_if_not_exist(directory):
    """If directory doesn't exist, created it."""
    if not os.path.exists(directory):
        os.makedirs(directory)


def validate_autogen_columns(autogen_columns):
    """Ensure autogen_column choice is valid."""
    for agc in autogen_columns:
        if agc not in VALID_AUTOGEN_COLUMNS:
            raise Exception("Bork! autogen column {} invalid!".format(agc))


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


def validate_type(message, value, truth_file, vartype):
    """Type validator for incoming data structures loaded from YAML file."""
    if not isinstance(value, vartype):
        raise Exception("{} must be {}, Got {} in {}".format(
            message, vartype, type(value), truth_file))


class HikingList(object):
    def __init__(self, peaks, location, filename, standalone, cascading,
                 ordered_columns=[], maximum=0, sortby='Elevation',
                 explicit_columns=False, peakcountlist=[], autogen_columns=[],
                 prominence_style=False, prominence_threshold=0):
        self.peaks = peaks
        self.maximum = maximum
        self.location = location
        self.cascading = cascading
        self.standalone = standalone
        self.filename = filename
        self.ordered_columns = ordered_columns
        self.sortby = sortby
        self.explicit_columns = explicit_columns
        self.autogen_columns = autogen_columns
        self.ascendingsort = False
        self.startingpoint = 1
        self.peakcountlist = peakcountlist
        self.prominence_style = prominence_style
        self.prominence_threshold = prominence_threshold
        self.pessimistic = False
        self.pessimism = 0
        self.optimistic = False
        self.optimism = 0

    @property
    def output_dir(self):
        """
        Output directory for any lists files created %CWD/lists/%location.
        """
        if self.cascading:
            subdir = "full"
        else:
            subdir = "abridged"
        if self.pessimistic:
            return '{}/lists/{}/{}/pessimistic/{}'.format(WORKING_DIR,
                                                          self.location,
                                                          self.filename,
                                                          subdir)
        if self.optimistic:
            return '{}/lists/{}/{}/optimistic/{}'.format(WORKING_DIR,
                                                         self.location,
                                                         self.filename,
                                                         subdir)

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
        # cull peaks that fail to meet the prominence_threshold
        self.cull_by_prominence_threshold()
        # sort the peaks list
        self.sort_by()
        # if we're not using cascading, figure out rank starting point and
        # maximum
        self.calculate_abridge_peak_list_length()
        # add any autogen columns
        self.generate_autogen_columns()
        # trim the peaks list
        self.trim_by_maximum()
        # validate columns, compare against what was passed in.
        self.format_data_structure()
        # print(self.tablib_data)

    def cull_by_prominence_threshold(self):
        """
        Cull peaks that fail to meet the digitally optimistic or
        pessimistic threshold.
        """
        def common(threshold, peaks=[]):
            valid = list()
            for peak in peaks:
                prom = peak.get('Prominence', 0)
                # no prominence data? We assume it's OK
                if not prom:
                    valid.append(peak)
                    continue
                if prom >= threshold:
                    valid.append(peak)
            return valid

        if not ((self.pessimistic or self.optimistic)
                 and self.prominence_threshold):
            self.peaks =\
                common(self.prominence_threshold, self.peaks)
            self.peakcountlist = \
                common(self.prominence_threshold, self.peakcountlist)

        if self.pessimistic:
            pessimistic_threshold =\
                self.prominence_threshold * (1+(self.pessimism/100))
            self.peaks =\
                common(pessimistic_threshold, self.peaks)
            self.peakcountlist = \
                common(self.prominence_threshold, self.peakcountlist)

        if self.optimistic:
            optimistic_threshold =\
                self.prominence_threshold * (1-(self.optimism/100))
            self.peaks =\
                common(optimistic_threshold, self.peaks)
            self.peakcountlist = \
                common(self.prominence_threshold, self.peakcountlist)

    def calculate_abridge_peak_list_length(self):
        """
        Changes the maximum to work with abridged lists
        This is achieved by first calculating the total number of unique
        imported peaks as a set of the entire peak set. Then subtracting that
        from the set maximum to find the accurate difference for the abridged
        set.
        """
        if self.prominence_style:
            return
        if self.peakcountlist:
            uniqueImportedPeaks = [dict(t) for t in set(frozenset(d.items())
                                   for d in self.peakcountlist)]
            uniqueProperPeaks = [dict(t) for t in set(frozenset(d.items())
                                 for d in self.peaks)]
            uniqueAllPeaks = [dict(t) for t in set(frozenset(d.items())
                              for d in uniqueProperPeaks +
                              uniqueImportedPeaks)]
            importLth = len(uniqueAllPeaks) - len(uniqueProperPeaks)
            abridgedLth = self.maximum - importLth
            self.startingpoint = importLth + 1
            if self.maximum:
                self.maximum = abridgedLth

    def generate_autogen_columns(self):
        """Function for calling any autogen columns."""
        for agc in self.autogen_columns:
            # Explicit columns on? this agc not one of them? Skip its ass.
            if self.explicit_columns and agc not in self.ordered_columns:
                continue
            if agc == "Rank":
                self.autogen_rank()
            if agc == "Meters":
                self.autogen_metric()

    def autogen_rank(self):
        """
        Generate a rank column.
        Data must be ordered before running this function or else you're going
        to be very very sad.
        """
        # Stick rank at the front of the list if its not already there.
        if 'Rank' not in self.ordered_columns:
            self.ordered_columns.insert(0, 'Rank')
        for index, peak in enumerate(self.peaks):
            peak['Rank'] = index + self.startingpoint

    def autogen_metric(self):
        """Generate a Metric Elevation column."""
        if 'Meters' not in self.ordered_columns:
            self.ordered_columns.append('Meters')
        for peak in self.peaks:
            peak['Meters'] = round(peak['Elevation'] * 0.3048)

    def remove_duplicate_peaks(self):
        """Remove all duplicate peak entries. Does not preserve ordering."""
        self.peaks = [dict(t) for t in set(frozenset(d.items())
                      for d in self.peaks)]

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
        """Throws exception if sortby column doesn't exist."""
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
        # If sorting by a non required column, figure out the datatype in case
        # we need to backfill.
        column_null_data = ""
        if self.sortby not in REQUIRED_COLUMNS:
            for peak in self.peaks:
                example_value = peak.get(self.sortby, None)
                if example_value:
                    if isinstance(example_value, int):
                        column_null_data = 0
                    elif isinstance(example_value, str):
                        column_null_data = ""
                    else:
                        raise Exception("Discovered sortable field "
                                        "must be string, or integer")
            for peak in self.peaks:
                if not peak.get(self.sortby, None):
                    peak[self.sortby] = column_null_data

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
        kmlFolder =\
            kml.Folder(ns,
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
