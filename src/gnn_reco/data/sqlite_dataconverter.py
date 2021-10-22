from glob import glob
from multiprocessing import Pool
import numpy as np
import os
import pandas as pd
import sqlalchemy
import sqlite3
from tqdm import tqdm
from typing import List

try:
    from icecube import icetray, dataio  # pyright: reportMissingImports=false
except ImportError:
    print("icecube package not available.")

from .dataconverter import DataConverter
from .utils import create_out_directory, pairwise_shuffle


class SQLiteDataConverter(DataConverter):
    def __init__(self, outdir, pulsemap, gcd_rescue, *, db_name, workers, max_dictionary_size=10000, verbose=1):
        """Implementation of DataConverter for saving to SQLite database.

        Converts the i3-files in paths to several temporary SQLite databases in 
        parallel, that are then merged to a single SQLite database

        Args:
            outdir (str): the directory to which the SQLite database is written
            pulsemap (str): the pulsemap chosen for extraction. e.g. 
                SRTInIcePulses.
            gcd_rescue (str): path to gcd_file that the extraction defaults to 
                if none is found in the folders
            db_name (str): database name. please omit extensions.
            workers (int): number of workers used for parallel extraction.
            max_dictionary_size (int, optional): The maximum number of events in 
                a temporary database. Defaults to 10000.
            verbose (int, optional): Silent extraction if 0. Defaults to 1.
        """
        # Additional member variables
        self._db_name        = db_name
        self._verbose        = verbose
        self._workers        = workers
        self._max_dict_size  = max_dictionary_size 
        
        # Base class constructor
        super().__init__(outdir, pulsemap, gcd_rescue)
        
    # Abstract method implementation(s)
    def _process_files(self, i3_files, gcd_files):
        """Starts the parallelized extraction using map_async.
        """
               
        create_out_directory(self._outdir + '/%s/data'%self._db_name)
        create_out_directory(self._outdir + '/%s/tmp'%self._db_name)
        
        i3_files, gcd_files = pairwise_shuffle(i3_files, gcd_files)
        self._save_filenames(i3_files)
        
        workers = min(self._workers, len(i3_files))
        
        # SETTINGS
        settings = []
        event_nos = np.array_split(np.arange(0,99999999,1),workers)  # Notice that this choice means event_no is NOT unique between different databases.
        file_list = np.array_split(np.array(i3_files),workers)
        gcd_file_list = np.array_split(np.array(gcd_files),workers)
        for i in range(workers):
            settings.append([
                file_list[i],
                str(i),
                gcd_file_list[i], 
                event_nos[i], 
                self._max_dict_size, 
                self._db_name, 
                self._outdir,
            ])
        
        print(f"Starting pool of {workers} workers to process {len(i3_files)} I3 files")
        p = Pool(processes=workers)
        p.map_async(self._parallel_extraction, settings)
        p.close()
        p.join()
        print('Merging databases')
        self._merge_databases()
        
    
    def _initialise(self):
        if self._verbose == 0:
            icetray.I3Logger.global_logger = icetray.I3NullLogger()

    def _save(self, array, out_file):
        # Not used
        pass


    # Non-inherited private method(s)
    def _parallel_extraction(self, settings):
        """The function that every worker runs. 
        
        Extracts feature, truth and RetroReco (if available) and saves it as temporary sqlite databases.

        Args:
            settings (list): List of arguments.
        """
        input_files,id, gcd_files, event_no_list, max_dict_size, db_name, outdir = settings
        event_counter = 0
        feature_big = pd.DataFrame()
        truth_big   = pd.DataFrame()
        retro_big   = pd.DataFrame()
        file_counter = 0
        output_count = 0
        gcd_count = 0
        for u in range(len(input_files)):
            self._extractors.set_files(input_files[u], gcd_files[u])
            i3_file = dataio.I3File(input_files[u], "r")

            while i3_file.more():
                try:
                    frame = i3_file.pop_physics()
                except:
                    frame = False
                if frame:
                    truths, features, retros = self._extractors(frame)
                    truth    = apply_event_no(truths, event_no_list, event_counter)
                    truth_big   = truth_big.append(truth, ignore_index = True, sort = True)
                    if len(retros)>0:
                        retro   = apply_event_no(retros, event_no_list, event_counter)
                        retro_big   = retro_big.append(retro, ignore_index = True, sort = True)
                    if not is_empty(features):
                        features = apply_event_no(features, event_no_list, event_counter)
                        feature_big= feature_big.append(features,ignore_index = True, sort = True)
                    event_counter += 1
                    if len(truth_big) >= max_dict_size:
                        save_to_sql(feature_big, truth_big, retro_big, id, output_count, db_name, outdir, self._pulsemap)

                        feature_big = pd.DataFrame()
                        truth_big   = pd.DataFrame()
                        retro_big   = pd.DataFrame()
                        output_count +=1
            file_counter +=1
        if len(truth_big) > 0:
            save_to_sql(feature_big, truth_big, retro_big, id, output_count, db_name, outdir, self._pulsemap)
            feature_big = pd.DataFrame()
            truth_big   = pd.DataFrame()
            retro_big   = pd.DataFrame()
            output_count +=1
        
    def _save_filenames(self, i3_files: List[str]):
        """Saves I3 file names in CSV format."""
        create_out_directory(self._outdir + '/%s/config'%self._db_name)
        i3_files = pd.DataFrame(data=i3_files, columns=['filename'])
        i3_files.to_csv(self._outdir + '/%s/config/i3files.csv'%self._db_name)
        
    def _merge_databases(self):
        """Merges the temporary databases into a single sqlite database, then deletes the temporary databases."""
        path_tmp = self._outdir + '/' + self._db_name + '/tmp'
        database_path = self._outdir + '/' + self._db_name + '/data/' + self._db_name
        db_files = glob(os.path.join(path_tmp, '*.db'))
        db_files = [os.path.split(db_file)[1] for db_file in db_files]
        if len(db_files) > 0:
            print('Found %s .db-files in %s'%(len(db_files),path_tmp))
            print(db_files)
            truth_columns, pulse_map_columns, retro_columns = self._extract_column_names(path_tmp, db_files, self._pulsemap)
            self._create_empty_tables(database_path,self._pulsemap, truth_columns, pulse_map_columns, retro_columns)
            self._merge_temporary_databases(database_path, db_files, path_tmp, self._pulsemap)
            os.system('rm -r %s'%path_tmp)
        else:
            print('No temporary database files found!')

    def _extract_column_names(self,tmp_path, db_files, pulsemap):
        db = tmp_path + '/' + db_files[0]
        with sqlite3.connect(db) as con:
            truth_query = 'select * from truth limit 1'
            truth_columns = pd.read_sql(truth_query,con).columns

        with sqlite3.connect(db) as con:
            pulse_map_query = 'select * from %s limit 1'%pulsemap
            pulse_map = pd.read_sql(pulse_map_query,con)
        pulse_map_columns = pulse_map.columns
        
        for db_file in db_files:
            db = tmp_path + '/' + db_file
            try:
                with sqlite3.connect(db) as con:
                    retro_query = 'select * from RetroReco limit 1'
                    retro_columns = pd.read_sql(retro_query,con).columns
                if len(retro_columns)>0:
                    break
            except:
                retro_columns = []
        return truth_columns, pulse_map_columns, retro_columns

    def _run_sql_code(self, database: str, code: str):
        conn = sqlite3.connect(database + '.db')
        c = conn.cursor()
        c.executescript(code)
        c.close()  

    def _attach_index(self, database: str, table_name: str):
        """Attaches the table index. Important for query times!"""
        code = (
            "PRAGMA foreign_keys=off;\n"
            "BEGIN TRANSACTION;\n"
            f"CREATE INDEX event_no_{table_name} ON {table_name} (event_no);\n"
            "COMMIT TRANSACTION;\n"
            "PRAGMA foreign_keys=on;"
        )
        self._run_sql_code(database, code)

    def _create_table(self, database, table_name, columns, is_pulse_map=False):
        """Creates a table.

        Args:
            database (str): path to the database
            table_name (str): name of the table
            columns (str): the names of the columns of the table
            is_pulse_map (bool, optional): whether or not this is a pulse map table. Defaults to False.
        """
        count = 0
        for column in columns:
            if count == 0:
                if column == 'event_no':
                    if is_pulse_map == False:
                        query_columns =  column + ' INTEGER PRIMARY KEY NOT NULL'
                    else:
                        query_columns =  column + ' NOT NULL'
                else: 
                    query_columns =  column + ' FLOAT'
            else:
                if column == "event_no":
                    if is_pulse_map == False:
                        query_columns =  query_columns + ', ' + column + ' INTEGER PRIMARY KEY NOT NULL'
                    else:
                        query_columns = query_columns + ', '+ column + ' NOT NULL' 
                else:
                    query_columns = query_columns + ', ' + column + ' FLOAT'

            count +=1
        code = (
            "PRAGMA foreign_keys=off;\n"
            f"CREATE TABLE {table_name} ({query_columns});\n"
            "PRAGMA foreign_keys=on;"
        )
        self._run_sql_code(database, code)
        if is_pulse_map:
            print(table_name)
            print('attaching indexs')
            self._attach_index(database,table_name)
        return

    def _create_empty_tables(self,database,pulse_map,truth_columns, pulse_map_columns, retro_columns):
        """Creates an empty table

        Args:
            database (str): path to database
            pulse_map (str): the pulse map key e.g. SR
            truth_columns ([type]): [description]
            pulse_map_columns ([type]): [description]
            retro_columns ([type]): [description]
        """
        print('Creating Empty Truth Table')
        self._create_table(database, 'truth', truth_columns, is_pulse_map=False) # Creates the truth table containing primary particle attributes and RetroReco reconstructions
        print('Creating Empty RetroReco Table')
        if len(retro_columns) > 1:
            self._create_table(database, 'RetroReco',retro_columns, is_pulse_map=False) # Creates the RetroReco Table with reconstuctions and associated values.

        self._create_table(database, pulse_map,pulse_map_columns, is_pulse_map=True)
        return

    def _submit_to_database(self, database: str, key: str, data: pd.DataFrame):
        """Submits data to the database with specified key."""
        if len(data) == 0:
            if self._verbose:
                print(f"No data provided for {key}.")
                pass
            return
        engine = sqlalchemy.create_engine('sqlite:///' + database + '.db')
        data.to_sql(key, engine,index=False, if_exists='append')
        engine.dispose()

    def _extract_everything(self, db, pulsemap):
        """Extracts everything from the temporary database db

        Args:
            db (str): path to temporary database
            pulsemap (str): name of the pulsemap. E.g. SRTInIcePulses

        Returns:
            truth (pandas.DataFrame()): contains the truth data
            features (pandas.DataFame()): contains the pulsemap
            retro (pandas.DataFrame) : contains RetroReco and associated quantities if available
        """
        with sqlite3.connect(db) as con:
            truth_query = 'select * from truth'
            truth = pd.read_sql(truth_query,con)
        with sqlite3.connect(db) as con:
            pulse_map_query = 'select * from %s'%pulsemap
            features = pd.read_sql(pulse_map_query,con)

        try:
            with sqlite3.connect(db) as con:
                retro_query = 'select * from RetroReco'
                retro = pd.read_sql(retro_query,con)
        except:
            retro = []
        return truth, features, retro

    def _merge_temporary_databases(self,database, db_files, path_to_tmp, pulse_map):
        """Merges the temporary databases

        Args:
            database (str): path to the final database
            db_files (list): list of names of temporary databases
            path_to_tmp (str): path to temporary database directory
            pulse_map (str): name of the pulsemap. E.g. SRTInIcePulses
        """
        for i in tqdm(range(len(db_files)), colour='green'):
            file = db_files[i]
            truth, features, retro = self._extract_everything(path_to_tmp + '/'  + file,pulse_map)
            self._submit_to_database(database, "truth", truth)
            self._submit_to_database(database, pulse_map, features)
            self._submit_to_database(database, "RetroReco", retro)
            


# Implementation-specific utility function(s)
def apply_event_no(extraction, event_no_list, event_counter):
    """Converts extraction to pandas.DataFrame and applies the event_no index to extraction

    Args:
        extraction (dict): Dictionary with the extracted data.
        event_no_list (list): List of allocated event_no's.
        event_counter (int): Index for event_no_list.

    Returns:
        out (pandas.DataFrame): Extraction as pandas.DataFrame with event_no column.
    """
    out = pd.DataFrame(extraction.values()).T
    out.columns = extraction.keys()
    out['event_no'] = event_no_list[event_counter]
    return out

def is_empty(features):
    if features['dom_x'] != None:
        return False
    else:
        return True

def save_to_sql(feature_big, truth_big, retro_big, id, output_count, db_name,outdir, pulsemap):
    engine = sqlalchemy.create_engine('sqlite:///'+outdir + '/%s/tmp/worker-%s-%s.db'%(db_name,id,output_count))
    truth_big.to_sql('truth',engine,index= False, if_exists = 'append')
    if len(retro_big)> 0:
        retro_big.to_sql('RetroReco',engine,index= False, if_exists = 'append')
    feature_big.to_sql(pulsemap,engine,index= False, if_exists = 'append')
    engine.dispose()
    return