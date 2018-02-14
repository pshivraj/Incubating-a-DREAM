from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
import os
import subprocess
from distutils.dir_util import remove_tree
import shutil
import time
import spotpy
import pandas as pd
import numpy as np

import matplotlib.pyplot as plt
plt.switch_backend('agg')

def plot_results(results, threshold=0.2):
    names = []
    values = []
    no_names = []
    no_values = []
    index = []
    no_index = []

    parnames = spotpy.analyser.get_parameternames(results)
    sensitivity_data = spotpy.analyser.get_sensitivity_of_fast(results,M=2)
    sensitivity_data = list(sensitivity_data.values())[1]
    
    with open('sensitivity_data.txt', 'w') as f:
        f.writelines([str(s) + "\n" for s in sensitivity_data])

    for j in range(len(sensitivity_data)):
        if sensitivity_data[j] > threshold:
            names.append(parnames[j])
            values.append(sensitivity_data[j])
            index.append(j)
        else:
            no_names.append(parnames[j])
            no_values.append(sensitivity_data[j])
            no_index.append(j)

    fig = plt.figure(figsize=(16,6))
    ax = plt.subplot(1,1,1)
    ax.bar(index, values, align='center')
    ax.bar(no_index, no_values, color='orange', label = 'Insensitive parameter')

    ax.plot(np.arange(-1,len(parnames)+1,1),[threshold]*(len(parnames)+2),'r--')
    plt.xticks(list(range(len(sensitivity_data))), parnames)
    plt.setp(ax.get_xticklabels(), fontsize=10)
    fig.savefig('FAST_sensitivity.png',dpi=300)

#Function to write to DHSVM config file simulated inputs from DREAM.
def change_setting(config_file, setting_name, new_value, occurrence_loc='g'):
    sed_cmd = "sed -i 's:{setting_name} = .*:{setting_name} = {new_value}:{occurrence_loc}' {config_file}"
    sed_cmd = sed_cmd.format(setting_name = setting_name, new_value = new_value
                             , config_file = config_file
                             , occurrence_loc = occurrence_loc)
    return subprocess.call(sed_cmd, shell=True)

#Files and their input paths

config_file = 'Input.sauk.wrf.dynG.global.2006flood'
streamflow_only = 'output/DHSVMoutput_wrf_global_2006flood/Streamflow.Only'
validation_csv = 'validation.csv'
dhsvm_cmd = 'DHSVM3.1.3 ' + config_file 
DIR_PREFIX = "dhsvm_run_4_data_pid_"

# Cheap logging
def log(s):
    print(time.asctime() + " ({})".format(os.getpid()) + ": " + str(s))

class fast_run_setup(object):
    def __init__(self, parallel='seq'):

        self.params = [spotpy.parameter.Uniform('Lateral_Conductivity_61',low=0.00001 , high=0.01,  optguess=0.0017),
                       spotpy.parameter.Uniform('Exponential_Decrease_61',low=0.25 , high=2.5,  optguess=0.5),
                       spotpy.parameter.Uniform('Lateral_Conductivity_62',low=0.00001, high=0.01,  optguess=0.00017),
                       spotpy.parameter.Uniform('Exponential_Decrease_62',low=0.25, high=2.5,  optguess=0.5),
                       spotpy.parameter.Uniform('Precipitation_Lapse_Rate',low=0.0001 , high=0.001,  optguess=0.0006),
                       spotpy.parameter.Uniform('Temperature_Lapse_Rate',low=-0.0025 , high=-0.008,  optguess=-0.0048),
                       spotpy.parameter.Uniform('Precipitation_Multiplier',low=0.000005, high=0.00003,  optguess=0.00001),
                       spotpy.parameter.Uniform('Maximum_Resistance_9',low=500, high=3000,  optguess=3000),
                       spotpy.parameter.Uniform('Minimum_Resistance_9',low=150, high=300,  optguess=250),
                       spotpy.parameter.Uniform('Overstory_Monthly_LAI_9',low=0.5, high=6,  optguess=0.5)
                       ]
        evaluation = pd.read_csv(validation_csv)
        self.evals = evaluation['value'].values
        print(len(self.evals))
        self.parallel = parallel

    def parameters(self):
        return spotpy.parameter.generate(self.params)
    
    #setting up simulation for location:12189500 with predefined params and writing to config file 
    def simulation(self, x):
        pid = str(os.getpid())
        log("Initiating Copy for Process {}".format(pid))
        child_dir = "./" + DIR_PREFIX + pid
        #copy_tree(".", child_dir)
        shutil.copytree(".", child_dir, ignore=shutil.ignore_patterns(DIR_PREFIX + "*"))
              
        log("Copy for Process {} completed".format(pid))
        
        log("Forking into " + child_dir)
        os.chdir(child_dir)
        
        #write DREAM parameter input to config file.
        change_setting(config_file, "Lateral Conductivity 61", str(round(x[0],5)))
        change_setting(config_file, "Exponential Decrease 61", str(round(x[1],5)))
        change_setting(config_file, "Lateral Conductivity 62", str(round(x[2],5)))
        change_setting(config_file, "Exponential Decrease 62", str(round(x[3],5)))
        change_setting(config_file, "Maximum Infiltration 61", str(round(x[0]/10,5)))
        change_setting(config_file, "Vertical Conductivity 61"," ".join([str(round(x[0]/10,5))]*3))
        change_setting(config_file, "Maximum Infiltration 62", str(round(x[2]/10,5)))
        change_setting(config_file, "Vertical Conductivity 62"," ".join([str(round(x[2]/10,5))]*3))
        change_setting(config_file, "Precipitation Lapse Rate", str(round(x[2],5)))
        change_setting(config_file, "Temperature Lapse Rate", str(round(x[5],5)))
        change_setting(config_file, "Precipitation Multiplier", str(round(x[6],5)))
        change_setting(config_file, "Maximum Resistance       9", str(round(x[7],5)) +' '+ str(round(x[7]/1.66,5)))
        change_setting(config_file, "Minimum Resistance       9", str(round(x[8],5)) +' '+ str(round(x[8]/1.25,5)))
        change_setting(config_file, "Overstory Monthly Alb    9", " ".join([str(round(x[9]/10,5))]*12))
        #run DHSVM with modified parameters in config file
        retcode = subprocess.call(dhsvm_cmd, shell=True)
        log("Ran DHSVM: " + str(retcode))
        simulations=[]
        #read streamflow data from DHSVM output file
        with open(streamflow_only, 'r') as file_output:
            header_name = file_output.readlines()[0].split(' ')

        with open(streamflow_only) as inf:
            next(inf)
            date_q = []
            q_12189500 = []
            for line in inf:
                parts = line.split()
                if len(parts) > 1:
                    date_q.append(parts[0])
                    q_12189500.append(float(parts[2])/(3600*3))
                    
        os.chdir("..")
        log("Removing copied directory: " + str(child_dir))
        remove_tree(child_dir)
        log("Removed directory: " + str(child_dir))

        simulation_streamflow = pd.DataFrame({'x[0]':date_q, 'x[2]':q_12189500})
        simulation_streamflow.columns = [header_name[0], header_name[2]]
        simulation_streamflow = simulation_streamflow[:-14]
        log(simulation_streamflow.shape)
        simulations = simulation_streamflow['12189500'].values
        return simulations
    
    def evaluation(self):
        return self.evals.tolist()
    
    def objectivefunction(self, simulation, evaluation, params=None):
        model_fit = spotpy.objectivefunctions.nashsutcliffe(evaluation,simulation)
        log('Nashsutcliffe: ' + str(model_fit))
        return model_fit

# Initialize the Dream Class
fast_run = fast_run_setup()

log("Starting...")
# N = 1284s
# Create the Dream sampler of spotpy, al_objfun is set to None to force SPOTPY
# to jump into the def objectivefunction in the Dream_run_setup class with 
# nashsutcliffe as objectivefunction.
sampler=spotpy.algorithms.fast(fast_run, dbname='fast_dhsvm_soil_parallel_run', dbformat='ram', parallel='mpc')

sampler.sample(48)

results = sampler.getdata()
results_data = pd.DataFrame(results)
results_data.to_csv('fast_sensitive_params.csv')

plot_results(results)
