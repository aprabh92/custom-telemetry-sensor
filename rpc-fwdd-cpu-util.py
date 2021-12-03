#!/usr/bin/python
# Action script for creating structured xml output for the unstructured PFE command to view per CPU utilization of vSRX
import sys
import re
from jnpr.junos import Device
from jnpr.junos.exception import *
from lxml.etree import ElementTree
from lxml.etree import Element, SubElement
from lxml.etree import tostring

# Find regex match and return as list. Try to generalize search patterns for diff unstructured outputs
def regexMatch(regex, string):
    list_val=re.findall(regex, string)
    return list_val

# WIP:Feed the matched regex value into mode (io or cpu) Generazlie this! 
def xmlCreate(list_val):
    root = Element('customFwddCpu')
    for val in list_val:
        val_dict = {}
        val_dict['cpu-num']=val.split()[0]
        val_dict['util']=val.split()[1]
        val_dict['wutil']=val.split()[2]
        val_dict['status']=val.split()[3]
        val_dict['schedcounter']=val.split()[4]
        child=SubElement(root, 'cpu')
        for key,value in val_dict.items():
            subchild=SubElement(child, key)
            subchild.text = value 
    return tostring(root)

# Execute RPC calls on PFE
def execRPC(match):
    with Device(host='localhost', user='root', passwd='juniper123') as dev:
        if(match == 'cpu'):
            _val = dev.rpc.request_pfe_execute(target='fwdd', command='show i386 cpu')
    return tostring(_val)
 
def main():
    rpc_output_xml = execRPC('cpu')
    list_val = regexMatch(r'\d+\s+\d+\s+\d+\s+\w+\s+\d+', str(rpc_output_xml))
    final = xmlCreate(list_val)
    # Print is mandatory, else values would not be displayed.
    print(final)

if __name__ == '__main__':
    main()    
