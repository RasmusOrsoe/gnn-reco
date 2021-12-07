import pandas as pd
import matplotlib.pyplot as plt
import sqlite3
import numpy as np
from pathlib import Path
from scipy import stats

def add_energy(db,df):
    try:
        df['energy']
        return df
    except:
        events  = df['event_no']
        with sqlite3.connect(db) as con:
            query = 'select event_no, energy from truth where event_no in %s'%str(tuple(events))
            data = pd.read_sql(query,con).sort_values('event_no').reset_index(drop = True)
            
        df = df.sort_values('event_no').reset_index(drop = 'True')
        df['energy'] =  data['energy']
        return df

def add_signature(db, df):
    events  = df['event_no']
    with sqlite3.connect(db) as con:
        query = 'select event_no, pid, interaction_type from truth where event_no in %s'%str(tuple(events))
        data = pd.read_sql(query,con).sort_values('event_no').reset_index(drop = True)
        
    df = df.sort_values('event_no').reset_index(drop = 'True')
    df['signature'] =  int((abs(data['pid']) == 14) & (data['interaction_type'] == 1))
    return df

def add_pid_and_interaction(db, df):
    events  = df['event_no']
    with sqlite3.connect(db) as con:
        query = 'select event_no, pid, interaction_type from truth where event_no in %s'%str(tuple(events))
        data = pd.read_sql(query,con).sort_values('event_no').reset_index(drop = True)
        
    df = df.sort_values('event_no').reset_index(drop = True)
    df['interaction_type'] = data['interaction_type']
    df['pid'] = data['pid']

    for variable in df.columns:
        if variable == 'energy':
            df[variable] = np.log10(df[variable])
            if variable+'_pred' in df.keys():
                df[variable + '_pred'] = np.log10(df[variable + '_pred'])
            if variable+'_retro' in df.keys():
                df[variable + '_retro'] = np.log10(df[variable + '_retro'])
    return df

def calculate_width(bias_tmp):
    return (np.percentile(bias_tmp,84) - np.percentile(bias_tmp,16))/2
    #return (np.percentile(bias_tmp,75) - np.percentile(bias_tmp,25))/1.365

def gauss_pdf(mean, std, x):
    pdf =  1/(std*np.sqrt(2*np.pi)) * np.exp(-(1/2)*((x-mean)/std)**2)
    return (pdf).reset_index(drop = True)

def empirical_pdf(x,diff):
    dist = getattr(stats, 'norm')
    parameters = dist.fit(diff)
    pdf = gauss_pdf(parameters[0],parameters[1],diff)[x]
    #print(pdf)
    return pdf

def calculate_width_error(diff):
    N = len(diff)
    x_16 = abs(diff-np.percentile(diff,16,interpolation='nearest')).argmin() #int(0.16*N)
    x_84 = abs(diff-np.percentile(diff,84,interpolation='nearest')).argmin() #int(0.84*N)
    fe_16 = sum(diff <= diff[x_16])/N
    fe_84 = sum(diff <= diff[x_84])/N
    n_16 = sum(diff <= diff[x_16])
    n_84 = sum(diff <= diff[x_84]) 
    #error_width = np.sqrt((0.16*(1-0.16)/N)*(1/fe_16**2 + 1/fe_84**2))*(1/2)
    #n,bins,_ = plt.hist(diff, bins = 30)
    #plt.close()
    if len(diff)>0:
        error_width = np.sqrt((1/empirical_pdf(x_84, diff)**2)*(0.84*(1-0.84)/N) + (1/empirical_pdf(x_16, diff)**2)*(0.16*(1-0.16)/N))*(1/2)
    else:
        error_width = np.nan
    return error_width
   
def check_for_retro(data):
    columns = data.columns
    is_retro = False
    for column in columns:
        if 'retro' in column:
            is_retro = True
            break
    return is_retro

def extract_statistics(data,keys, key_bins):
    data = data.sort_values('event_no').reset_index(drop = 'True')
    pids = pd.unique(abs(data['pid']))
    is_retro = check_for_retro(data)
    interaction_types = data['interaction_type'].unique()
    biases = {}
    if is_retro:
        post_fix = '_retro'
    else:
        post_fix = '_pred'
    for key in keys:
        biases[key] = {}
        if key != 'energy':
            data[key] = data[key]*(360/(2*np.pi))
            data[key + post_fix] = data[key + post_fix]*(360/(2*np.pi))
        for pid in pids:
            biases[key][str(pid)] = {}
            data_pid_indexed = data.loc[abs(data['pid']) == pid,:].reset_index(drop = True)
            for interaction_type in interaction_types:
                biases[key][str(pid)][str(interaction_type)] = {'mean':         [],
                                                                '16th':         [],
                                                                '50th':         [],
                                                                '84th':         [],
                                                                'count':        [],
                                                                'width':        [],
                                                                'width_error':  [],
                                                                'predictions' : [],
                                                                'bias': []}
                data_interaction_indexed = data_pid_indexed.loc[data_pid_indexed['interaction_type'] == interaction_type,:]
                if len(data_interaction_indexed) > 0:
                    biases[key][str(pid)][str(interaction_type)]['predictions'] = data_interaction_indexed[key + post_fix].values.ravel()
                    if key == 'energy':
                        biases[key][str(pid)][str(interaction_type)]['bias'] = ((10**data_interaction_indexed[key +  post_fix] - 10**data_interaction_indexed[key])/(10**data_interaction_indexed[key])).values.ravel()
                    if key == 'zenith':
                        biases[key][str(pid)][str(interaction_type)]['bias'] = (data_interaction_indexed[key +  post_fix] - data_interaction_indexed[key]).values.ravel()
                bins = key_bins['energy']
                #
                for i in range(1,(len(bins))):
                    bin_index  = (data_interaction_indexed['energy'] > bins[i-1]) & (data_interaction_indexed['energy'] < bins[i])
                    data_interaction_indexed_sliced = data_interaction_indexed.loc[bin_index,:].sort_values('%s'%key).reset_index(drop  = True) 
                    
                    if key == 'energy':
                        bias_tmp_percent = ((10**(data_interaction_indexed_sliced[key + post_fix])- 10**(data_interaction_indexed_sliced[key]))/10**(data_interaction_indexed_sliced[key]))*100
                        bias_tmp = data_interaction_indexed_sliced[key +  post_fix] - data_interaction_indexed_sliced[key]
                    else:
                        bias_tmp = data_interaction_indexed_sliced[key +  post_fix]- data_interaction_indexed_sliced[key]
                        if key == 'azimuth':
                            bias_tmp[bias_tmp>= 180] = 360 - bias_tmp[bias_tmp>= 180]
                            bias_tmp[bias_tmp<= -180] = -(bias_tmp[bias_tmp<= -180] + 360)
                    if len(data_interaction_indexed_sliced)>0:
                        biases[key][str(pid)][str(interaction_type)]['mean'].append(np.mean(data_interaction_indexed_sliced['energy']))
                        
                        #biases[key][str(pid)][str(interaction_type)]['count'].append(len(bias_tmp))
                        #biases[key][str(pid)][str(interaction_type)]['width'].append(CalculateWidth(bias_tmp))
                        #biases[key][str(pid)][str(interaction_type)]['width_error'].append(CalculateWidthError(bias_tmp))
                        if key == 'energy':
                            biases[key][str(pid)][str(interaction_type)]['width'].append(calculate_width(bias_tmp_percent))
                            biases[key][str(pid)][str(interaction_type)]['width_error'].append(calculate_width_error(bias_tmp_percent))
                            biases[key][str(pid)][str(interaction_type)]['16th'].append(np.percentile(bias_tmp_percent,16))
                            biases[key][str(pid)][str(interaction_type)]['50th'].append(np.percentile(bias_tmp_percent,50))
                            biases[key][str(pid)][str(interaction_type)]['84th'].append(np.percentile(bias_tmp_percent,84))
                        else:
                            biases[key][str(pid)][str(interaction_type)]['width'].append(calculate_width(bias_tmp))
                            biases[key][str(pid)][str(interaction_type)]['width_error'].append(calculate_width_error(bias_tmp))
                            biases[key][str(pid)][str(interaction_type)]['16th'].append(np.percentile(bias_tmp,16))
                            biases[key][str(pid)][str(interaction_type)]['50th'].append(np.percentile(bias_tmp,50))
                            biases[key][str(pid)][str(interaction_type)]['84th'].append(np.percentile(bias_tmp,84))
        
        biases[key]['all_pid'] = {}
        for interaction_type in interaction_types:
            biases[key]['all_pid'][str(interaction_type)] = {'mean':         [],
                                                            '16th':         [],
                                                            '50th':         [],
                                                            '84th':         [],
                                                            'count':        [],
                                                            'width':        [],
                                                            'width_error':  [],
                                                            'predictions': []}
            data_interaction_indexed = data.loc[data['interaction_type'] == interaction_type,:]
            if len(data_interaction_indexed) > 0: 
                biases[key]['all_pid'][str(interaction_type)]['predictions'] = data_interaction_indexed[key + post_fix].values.ravel()
                if key == 'energy':
                    biases[key]['all_pid'][str(interaction_type)]['bias'] = ((10**data_interaction_indexed[key +  post_fix] - 10**data_interaction_indexed[key])/(10**data_interaction_indexed[key])).values.ravel()
                else:
                    biases[key]['all_pid'][str(interaction_type)]['bias'] = (data_interaction_indexed[key +  post_fix] - data_interaction_indexed[key]).values.ravel()
            bins = key_bins['energy']
            for i in range(1,(len(bins))):
                bin_index  = (data_interaction_indexed['energy'] > bins[i-1]) & (data_interaction_indexed['energy'] < bins[i])
                data_interaction_indexed_sliced = data_interaction_indexed.loc[bin_index,:].sort_values('%s'%key).reset_index(drop  = True) 
                
                if key == 'energy':
                    print(data_interaction_indexed_sliced[key + post_fix][0:5])
                    print(data_interaction_indexed_sliced[key][0:5])
                    bias_tmp_percent = ((10**(data_interaction_indexed_sliced[key + post_fix])- 10**(data_interaction_indexed_sliced[key]))/(10**(data_interaction_indexed_sliced[key])))*100
                    bias_tmp = data_interaction_indexed_sliced[key +  post_fix] - data_interaction_indexed_sliced[key]
                else:
                    bias_tmp = data_interaction_indexed_sliced[key +  post_fix]- data_interaction_indexed_sliced[key]
                if key == 'azimuth':
                    bias_tmp[bias_tmp>= 180] = 360 - bias_tmp[bias_tmp>= 180]
                    bias_tmp[bias_tmp<= -180] = (bias_tmp[bias_tmp<= -180] + 360)
                    if np.max(bias_tmp) > 180:
                        print(np.max(bias_tmp))
                if len(data_interaction_indexed_sliced)>0:
                    biases[key]['all_pid'][str(interaction_type)]['mean'].append(np.mean(data_interaction_indexed_sliced['energy']))
                    biases[key]['all_pid'][str(interaction_type)]['count'].append(len(bias_tmp))
                    if key == 'energy':
                        biases[key]['all_pid'][str(interaction_type)]['width'].append(calculate_width(bias_tmp_percent))
                        biases[key]['all_pid'][str(interaction_type)]['width_error'].append(calculate_width_error(bias_tmp_percent))
                        biases[key]['all_pid'][str(interaction_type)]['16th'].append(np.percentile(bias_tmp_percent,16))
                        biases[key]['all_pid'][str(interaction_type)]['50th'].append(np.percentile(bias_tmp_percent,50))
                        biases[key]['all_pid'][str(interaction_type)]['84th'].append(np.percentile(bias_tmp_percent,84))
                    else:
                        biases[key]['all_pid'][str(interaction_type)]['width'].append(calculate_width(bias_tmp))
                        biases[key]['all_pid'][str(interaction_type)]['width_error'].append(calculate_width_error(bias_tmp))
                        biases[key]['all_pid'][str(interaction_type)]['16th'].append(np.percentile(bias_tmp,16))
                        biases[key]['all_pid'][str(interaction_type)]['50th'].append(np.percentile(bias_tmp,50))
                        biases[key]['all_pid'][str(interaction_type)]['84th'].append(np.percentile(bias_tmp,84))
        
        biases[key]['cascade'] = {}
        biases[key]['cascade']                       = {'mean':         [],
                                                        '16th':         [],
                                                        '50th':         [],
                                                        '84th':         [],
                                                        'count':        [],
                                                        'width':        [],
                                                        'width_error':  [],
                                                        'predictions': []}
        data_interaction_indexed = data.loc[~((data['pid'] == 14.0) & (data['interaction_type'] == 1.0)) ,:]
        if len(data_interaction_indexed) > 0: 
            biases[key]['cascade']['predictions'] = data_interaction_indexed[key + post_fix].values.ravel()
            if key == 'energy':
                biases[key]['cascade']['bias'] = ((10**data_interaction_indexed[key +  post_fix] - 10**data_interaction_indexed[key])/(10**data_interaction_indexed[key])).values.ravel()
            else:
                biases[key]['cascade']['bias'] = (data_interaction_indexed[key +  post_fix] - data_interaction_indexed[key]).values.ravel()
        bins = key_bins['energy']
        for i in range(1,(len(bins))):
            bin_index  = (data_interaction_indexed['energy'] > bins[i-1]) & (data_interaction_indexed['energy'] < bins[i])
            data_interaction_indexed_sliced = data_interaction_indexed.loc[bin_index,:].sort_values('%s'%key).reset_index(drop  = True) 
            
            if key == 'energy':
                bias_tmp_percent = ((10**(data_interaction_indexed_sliced[key + post_fix])- 10**(data_interaction_indexed_sliced[key]))/(10**(data_interaction_indexed_sliced[key])))*100
                bias_tmp = data_interaction_indexed_sliced[key +  post_fix] - data_interaction_indexed_sliced[key]
            else:
                bias_tmp = data_interaction_indexed_sliced[key +  post_fix]- data_interaction_indexed_sliced[key]
            if key == 'azimuth':
                bias_tmp[bias_tmp>= 180] = 360 - bias_tmp[bias_tmp>= 180]
                bias_tmp[bias_tmp<= -180] = (bias_tmp[bias_tmp<= -180] + 360)
                if np.max(bias_tmp) > 180:
                    print(np.max(bias_tmp))
            if len(data_interaction_indexed_sliced)>0:
                biases[key]['cascade']['mean'].append(np.mean(data_interaction_indexed_sliced['energy']))
                biases[key]['cascade']['count'].append(len(bias_tmp))
                if key == 'energy':
                    biases[key]['cascade']['width'].append(calculate_width(bias_tmp_percent))
                    biases[key]['cascade']['width_error'].append(calculate_width_error(bias_tmp_percent))
                    biases[key]['cascade']['16th'].append(np.percentile(bias_tmp_percent,16))
                    biases[key]['cascade']['50th'].append(np.percentile(bias_tmp_percent,50))
                    biases[key]['cascade']['84th'].append(np.percentile(bias_tmp_percent,84))
                else:
                    biases[key]['cascade']['width'].append(calculate_width(bias_tmp))
                    biases[key]['cascade']['width_error'].append(calculate_width_error(bias_tmp))
                    biases[key]['cascade']['16th'].append(np.percentile(bias_tmp,16))
                    biases[key]['cascade']['50th'].append(np.percentile(bias_tmp,50))
                    biases[key]['cascade']['84th'].append(np.percentile(bias_tmp,84))
    return biases

def get_retro(data, keys,db):
    events = data['event_no']
    key_count = 0
    for key in keys:
        if key_count == 0:
            query_keys = 'event_no, %s'%(key + '_retro')
        else:
            query_keys = query_keys + ', ' + key + '_retro'
    with sqlite3.connect(db) as con:
        query = 'select %s  from RetroReco where event_no in %s'%(query_keys, str(tuple(events)))
        retro = pd.read_sql(query,con).sort_values('event_no').reset_index(drop = True)

    with sqlite3.connect(db) as con:
        query = 'select event_no, energy, zenith, azimuth from truth where event_no in %s'%(str(tuple(events)))
        energy = pd.read_sql(query,con).sort_values('event_no').reset_index(drop = True)
    retro['energy'] = energy['energy']
    retro['zenith'] = energy['zenith']
    retro['azimuth'] = energy['azimuth']
    retro = add_pid_and_interaction(db, retro)
    return retro
    
def calculate_statistics(data,keys, key_bins,db,include_retro = False):
    biases = {'dynedge': extract_statistics(data, keys, key_bins)}
    if include_retro:
        retro = get_retro(data,keys,db)
        biases['retro'] = extract_statistics(retro, keys, key_bins)
    return biases

def plot_biases(key_limits, biases, is_retro = False):
    key_limits = key_limits['bias']
    if is_retro:
        prefix = 'RetroReco'
    else:
        prefix = 'dynedge'
    for key in biases.keys():
        fig, ax = plt.subplots(2,3,figsize=(11.69,8.27))
        fig.suptitle('%s: %s'%(prefix,key), size = 30)
        pid_count = 0
        for pid in biases[key].keys():
            interaction_count = 0
            for interaction_type in biases[key][pid]:
                if interaction_type != str(0.0):
                    plot_data = biases[key][pid][interaction_type]
                    if len(plot_data['mean']) != 0:
                        
                        ax2 = ax[interaction_count,pid_count].twinx()
                        ax2.bar(x = (plot_data['mean']), height = plot_data['count'], 
                                alpha = 0.3, 
                                color = 'grey',
                                align = 'edge',
                                width = 0.25)
                        ax[interaction_count,pid_count].plot((plot_data['mean']), np.repeat(0, len(plot_data['mean'])), color = 'black', lw = 4)
                        ax[interaction_count,pid_count].plot((plot_data['mean']), plot_data['16th'], ls = '--', color = 'red', label = '16th')
                        ax[interaction_count,pid_count].plot((plot_data['mean']), plot_data['84th'], ls = '--', color = 'red', label = '84th')
                        ax[interaction_count,pid_count].plot((plot_data['mean']), plot_data['50th'], color = 'red', label = '50th')
                        
                        if pid == str(12.0):
                            pid_tag = 'e'
                        if pid == str(14.0):
                            pid_tag = 'u'
                        if pid == str(16.0):
                            pid_tag = 'T'
                        if interaction_type == str(1.0):
                            interaction_tag = 'cc'
                        if interaction_type == str(2.0):
                            interaction_tag = 'nc'
                        if interaction_type == str(0.0):
                            interaction_tag = 'unknown'
                            
                        plt.title('$\\nu_%s$ %s'%(pid_tag, interaction_tag), size = 20)
                        ax[interaction_count,pid_count].tick_params(axis='x', labelsize=10)
                        ax[interaction_count,pid_count].tick_params(axis='y', labelsize=10)
                        ax[interaction_count,pid_count].set_xlim(key_limits[key]['x'])
                        ax[interaction_count,pid_count].set_ylim(key_limits[key]['y'])
                        ax[interaction_count,pid_count].legend()
                        plt.tick_params(right=False,labelright=False)
                        
                        
                        
                        if (interaction_count == 0) & (pid_count == 0) or (interaction_count == 1) & (pid_count == 0):
                            ax[interaction_count,pid_count].set_ylabel('$\\frac{pred-truth}{truth}$ [%]', size = 20)
                        if (interaction_count != 0):
                            ax[interaction_count,pid_count].set_xlabel('$energy_{log10}$ GeV', size = 25)
                        interaction_count +=1
            pid_count +=1
    return fig
            


def PlotWidth(key_limits, biases):
    key_limits = key_limits['width']
    if 'retro' in biases.keys():
        contains_retro = True
    else:
        contains_retro = False
        
    for key in biases['dynedge'].keys():
        fig, ax = plt.subplots(2,3,figsize=(11.69,8.27))
        fig.suptitle('dynedge: %s'%key, size = 30)
        pid_count = 0
        for pid in biases['dynedge'][key].keys():
            interaction_count = 0
            for interaction_type in biases['dynedge'][key][pid]:
                if interaction_type != str(0.0):
                    plot_data = biases['dynedge'][key][pid][interaction_type]
                    if contains_retro:
                        plot_data_retro = biases['retro'][key][pid][interaction_type]
                    if len(plot_data['mean']) != 0:
                        
                        ax2 = ax[interaction_count,pid_count].twinx()
                        ax2.bar(x = (plot_data['mean']), height = plot_data['count'], 
                                alpha = 0.3, 
                                color = 'grey',
                                align = 'edge',
                                width = 0.25)
                        ax[interaction_count,pid_count].errorbar(plot_data['mean'],plot_data['width'],plot_data['width_error'],linestyle='dotted',fmt = 'o',capsize = 10, label = 'dynedge')
                        if contains_retro:
                            ax[interaction_count,pid_count].errorbar(plot_data_retro['mean'],plot_data_retro['width'],plot_data_retro['width_error'],linestyle='dotted',fmt = 'o',capsize = 10, label = 'RetroReco')

                        
                        if pid == str(12.0):
                            pid_tag = 'e'
                        if pid == str(14.0):
                            pid_tag = 'u'
                        if pid == str(16.0):
                            pid_tag = 'T'
                        if interaction_type == str(1.0):
                            interaction_tag = 'cc'
                        if interaction_type == str(2.0):
                            interaction_tag = 'nc'
                        if interaction_type == str(0.0):
                            interaction_tag = 'unknown'
                            
                        plt.title('$\\nu_%s$ %s'%(pid_tag, interaction_tag), size = 20)
                        ax[interaction_count,pid_count].tick_params(axis='x', labelsize=10)
                        ax[interaction_count,pid_count].tick_params(axis='y', labelsize=10)
                        ax[interaction_count,pid_count].set_xlim(key_limits[key]['x'])
                        ax[interaction_count,pid_count].set_ylim(key_limits[key]['y'])
                        ax[interaction_count,pid_count].legend()
                        plt.tick_params(right=False,labelright=False)
                        if (interaction_count == 0) & (pid_count == 0) or (interaction_count == 1) & (pid_count == 0):
                            ax[interaction_count,pid_count].set_ylabel('W($log_{10}$($\\frac{pred}{truth}$)) [GeV]', size = 20)
                        if (interaction_count != 0):
                            ax[interaction_count,pid_count].set_xlabel('$energy_{log10}$ GeV', size = 25) 
                        
                        interaction_count +=1
            pid_count +=1
    return fig

def PlotRelativeImprovement(key_limits, biases):
    key_limits = key_limits['rel_imp']        
    for key in biases['dynedge'].keys():
        fig, ax = plt.subplots(2,3,figsize=(11.69,8.27))
        fig.suptitle('dynedge: %s'%key, size = 30)
        pid_count = 0
        for pid in biases['dynedge'][key].keys():
            interaction_count = 0
            for interaction_type in biases['dynedge'][key][pid]:
                if interaction_type != str(0.0):
                    plot_data = biases['dynedge'][key][pid][interaction_type]
                    plot_data_retro = biases['retro'][key][pid][interaction_type]
                    if len(plot_data['mean']) != 0:  
                        ax2 = ax[interaction_count,pid_count].twinx()
                        ax2.bar(x = (plot_data['mean']), height = plot_data['count'], 
                                alpha = 0.3, 
                                color = 'grey',
                                align = 'edge',
                                width = 0.25)
                        ax[interaction_count,pid_count].plot(plot_data['mean'], np.repeat(0, len(plot_data['mean'])), color = 'black', lw = 4)

                        ax[interaction_count,pid_count].errorbar(plot_data['mean'],1 - np.array(plot_data['width'])/np.array(plot_data_retro['width']),marker='o', markeredgecolor='black')

                            
                        if pid == str(12.0):
                            pid_tag = 'e'
                        if pid == str(14.0):
                            pid_tag = 'u'
                        if pid == str(16.0):
                            pid_tag = 'T'
                        if interaction_type == str(1.0):
                            interaction_tag = 'cc'
                        if interaction_type == str(2.0):
                            interaction_tag = 'nc'
                        if interaction_type == str(0.0):
                            interaction_tag = 'unknown'
                            
                        plt.title('$\\nu_%s$ %s'%(pid_tag, interaction_tag), size = 20)
                        ax[interaction_count,pid_count].tick_params(axis='x', labelsize=10)
                        ax[interaction_count,pid_count].tick_params(axis='y', labelsize=10)
                        ax[interaction_count,pid_count].set_xlim(key_limits[key]['x'])
                        ax[interaction_count,pid_count].set_ylim(key_limits[key]['y'])
                        ax[interaction_count,pid_count].legend()
                        plt.tick_params(right=False,labelright=False)
                        if (interaction_count == 0) & (pid_count == 0) or (interaction_count == 1) & (pid_count == 0):
                            ax[interaction_count,pid_count].set_ylabel('Relative Improvement', size = 20)
                        if (interaction_count != 0):
                            ax[interaction_count,pid_count].set_xlabel('$energy_{log10}$ GeV', size = 25) 
                        
                        interaction_count +=1
            pid_count +=1
    return fig


def calculate_relative_improvement_error(relimp, w1, w1_sigma, w2, w2_sigma):
    sigma = np.sqrt((np.array(w1_sigma)/np.array(w1))**2 + (np.array(w2_sigma)/np.array(w2))**2)
    return sigma
