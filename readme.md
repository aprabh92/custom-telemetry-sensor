# Creating custom telemetry sensor for Juniper products 

We can create custom telemetry sensors, configurations, RPC calls on most of the Juniper platforms such as MX (vMX), PTX (vPTX), SRX (vSRX), cMGD and cRPD. The MGD that allows one to make configurations, or netconf calls is the same across all Juniper platforms. In fact it has now been extracted as a container. We can leverage the powerful features of MGD to solve unique problems for which a solution isn’t natively available. This increases the agility to develop and solve problems until the feature natively comes out in a later release using these custom scripts and models for which Juniper provides a framework. 

Today in vSRX 3.0 there is no cli operational command to retrieve per CPU utilization. There are no Telemetry sensors for this as well to subscribe and obtain information such that healthbot or any tool like prometheus can subscribe to. One way to retrieve this data is via netconf by polling the PFE. Healthbot can then digest this information. But this isn’t a custom telemetry sensor which can be exposed via gRPC. How does one do that ? Junipers MGD has an amazing framework to process all XML structured data and render it out to the user. Once can bring in custom configurations, RPC calls and even custom telemetry sensors. There are various tools to do that. 

A custom call always provides the schema using yang. So you would need to write a custom yang module. Juniper supports both Yang 1.1 (RFC 7950)  and yang 1.0 (RFC 6020) 

An action script is typically associated to provide an action for the custom operational command i.e. the operational RPC calls

A configuration script can be part of the action script to configure the respective hierarchy that one has defined in the yang as well. We can use this when we introduce custom RPC calls and want to take some action. Example is , to develop a custom yang for programming IPtable rules for cRPD/cMGD/BMS. The action script can read from the yang values and take necessary actions. 

A translation script is used in case one has an external model such as openconfig or openroadm to map to existing Junos functionalities. A good example would be to configure BGP neighbor using OpenConfig. When this is done, the translation script is used to configure the BGP neighbor on the Junos DDL side and hence the requirement of translation. 
i.e. External model —> Junos DDL

## vSRX 3.0 requirements 

* Per CPU utilization
    * root> request pfe execute target fwdd command "show i386 cpu"
* CPUs allocated for IO vs PFE
    * root> request pfe execute target fwdd command "show swrss io"

## Developing a custom operational command to fetch per CPU utilization.

As explained earlier, the vSRX 3.0 (on 19.2R1) does not provide any operational command to view per CPU utilization. However this is available on the PFE. One can retrieve the information by running the below command on PFE itself.

```
root@vsrx1# run request pfe execute target fwdd command "show i386 cpu"
================ tnp_0x1000080 ================
SENT: Ukern command: show i386 cpu


CPU   Util WUtil Status SchedCounter
1     0     0     alive  6511
2     0     0     alive  6511
3     0     0     alive  6511
Average [cpu0-2](  0) (  0)


root@vsrx1# run request pfe execute target fwdd command "show swrss io"
================ tnp_0x1000080 ================
SENT: Ukern command: show swrss io


 IO CPU   current usage   last usage   sched
 0            4            4          699680

```

The below method explains, how to use yang to expose a custom RPC call which behind the scenes executes the above command. The above output however is not xml structured as well and is typically enclosed in <output></output> as a complete string. The yang defines the xml schema and the action script structures the xml output matching the defined schema so that respective values are enclosed within the leaf tags. Note that only the “show i386 cpu” command has been demonstrated in this document . It can extended to any such PFE command which isn’t exposed to the cli.

Note: “Yang2dsdl" tool which is a branch from pyang can be used to validate the xml structure against the yang file as well. 

In addition to the above mentioned tool, Junos also validates the XML file based on yang using the below command. It is recommended to run this and validate if the xml is valid or not once loading the custom yang and RPC call.

root@vsrx1> show custom fwdd cpu | display xml validate
 
PASS: The emitted XML is VALID

### Custom Yang file

```
module rpc-fwdd-cpu {
    namespace "http://custom/fwdd";
    prefix "rpc-cli";


    /*
    import junos-extension-odl {
        prefix junos-odl;
    }
    */


    import junos-extension {
        prefix junos;
    }


    organization "Juniper Networks";


    description "Custom RPC call for Per CPU utilization which
                 creates xml structured output by using custom
                 schema. Typical output is not xml structured
                 and value is returned in <output></output>";


    contact "Aravind Prabhakar
             <mailto: aprabh@juniper.net>";


    rpc ipsec-fwdd {
        description " Obtain Per CPU utilization from PFE";


        junos:command 'show custom fwdd' {
            junos:action-execute {
                junos:script "rpc-fwdd-cpu-util.py";
            }
        }


        input {
            leaf cpu {
                type empty;
            }


            // Not used currently
            /*leaf io {
                type empty;
            }*/
        }


        output {
            container customFwddCpu {
                list cpu {
                    key cpu-num;
                    leaf cpu-num {
                        description "CPU number";
                        type uint8;
                    }
                    leaf util {
                        description "CPU Utilization";
                        type uint8;
                    }
                    leaf wutil {
                        type uint8;
                    }
                    leaf status {
                        type string;
                    }
                    leaf schedcounter {
                        type uint8;
                    }
                }
            }
        }
    }
}

```

In the above yang example. 
* The file is saved as rpc-ipsec-fwdd.yang 
* The RPC contains input and output blocks which define the schema 
* Mentions the action script to be used under Junos:script as rpc-fwdd-cpu-util.py

### Custom action script supporting the yang file 

```
aprabh@aprabh-mbp vsrx_custom_sensor % more rpc-fwdd-cpu-util.py

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

```

* The action script should be placed under /var/db/scripts/action 
* If the action script is loaded along with the yang file using “request system yang add…”, the script is automatically placed under the correct path
* The execRPC function runs the RPC call to fetch the per CPU utilization
* The function xmlCreate takes the output from execRPC as input and creates the xmlstructure as per the schema definition in the yang 

The schema defined in the yang is as below for the output . Based on the number of CPUs we iterate and form the xml accordingly. Since the yang output defines this , once created and if it is a valid xml the respective values are fed automatically into the correct leaf tags (i.e. cpu-num, util, wutil, status and schedcounter)
```
<customIpsecFwdd>
    <cpu>
        <cpu-num>1</cpu-num>
        <util>0</util>
        <wutil>0</wutil>
        <status>alive</status>
        <schedcounter>286126</schedcounter>
    </cpu>
</customIpsecFwdd>
```

#### Load the yang package 

Copy the yang file along with the action script onto /tmp of the vSRX/vMX/cRPD/cMGD and run the below command. In case of command validations , we must take care of that using when and must conditions in the yang as per RFC 6020/RFC 7950 and enable the below mentioned commands for xpath validations. 

```
root@vsrx1> request system yang add package custom-fwdd module /tmp/rpc-fwdd-cpu.yang action-script /tmp/rpc-fwdd-cpu-util.py
YANG modules validation : START
YANG modules validation : SUCCESS
Scripts syntax validation : START
Scripts syntax validation : SUCCESS
TLV generation: START
TLV generation: SUCCESS
Building schema and reloading /config/juniper.conf.gz ...
Restarting mgd ...

WARNING: cli has been replaced by an updated version:
CLI release 20200115.184344_builder.r1081273 built by builder on 2020-01-15 19:00:21 UTC
Restart cli using the new version ? [yes,no] (yes) yes


Restarting cli ...
```

#### Validate the package 

```
root@vsrx1> show system yang package
Package ID            :custom-fwdd
YANG Module(s)        :rpc-fwdd-cpu.yang
Action Script(s)      :rpc-fwdd-cpu-util.py
Translation Script(s) :*
Translation script status is disabled
```

#### Validate the RPC call

```
root@vsrx1> show custom fwdd cpu | display xml
<rpc-reply xmlns:junos="http://xml.juniper.net/junos/19.4R0/junos">
    <customFwddCpu>
        <cpu>
            <util>
                0
            </util>
            <status>
                alive
            </status>
            <schedcounter>
                298745
            </schedcounter>
            <wutil>
                0
            </wutil>
            <cpu-num>
                1
            </cpu-num>
        </cpu>
        <cpu>
            <util>
                0
            </util>
            <status>
                alive
            </status>
            <schedcounter>
                298745
            </schedcounter>
            <wutil>
                0
            </wutil>
            <cpu-num>
                2
            </cpu-num>
        </cpu>
        <cpu>
            <util>
                0
            </util>
            <status>
                alive
            </status>
            <schedcounter>
                298745
            </schedcounter>
            <wutil>
                0
            </wutil>
            <cpu-num>
                3
            </cpu-num>
        </cpu>
    </customFwddCpu>
    <cli>
        <banner></banner>
    </cli>
</rpc-reply>
```

#### Delete the custom package

```
root@vsrx1> request system yang delete custom
Building schema and reloading /config/juniper.conf.gz ...
Restarting mgd ...


WARNING: cli has been replaced by an updated version:
CLI release 20200115.184344_builder.r1081273 built by builder on 2020-01-15 19:00:21 UTC
Restart cli using the new version ? [yes,no] (yes) yes


Restarting cli ...
root@vsrx1>
```

## What is xmlproxyd and how to use it ?


Junos’s frame work to automate or create any open interface is build very well and follows xml which is easily machine readable. Along with the other opportunities to interact with Junos DDL using Yang and other inbuilt tools. Xmlproxyd is one such tool which allows to create netconf end points to in order to expose a custom telemetry sensor using Yang. Under the hoods it relies on Drend (Dynamic rendering of xml ) framework to get all the work done. The yang module *must* start with "xmlproxyd_ “ and the drend:source should be the exact xml tag name which gets emitted from the config or RPC.

In order to create a custom sensor for the above generated data, we use xmlproxyd. Below it the custom yang created so that. Ensure that “dr:source”names is exactly the same name of the xml tag emitted. This should match. 

For example dr:source cpu-num should be the same as <cpu-num></cpu-num> tag emitted in the above explanations. 

```
module xmlproxyd_customFwddCpu {
    prefix "rpc-cli-xmld";
    namespace "http://custom/fwdd";
    import drend {
        prefix dr;
    }


    grouping customFwddCpu {
        list cpu {
            dr:source cpu;
            key cpu-num;
            leaf cpu-num {
                description "CPU number";
                type string;
                dr:source cpu-num;
            }
            leaf util {
                description "CPU Utilization";
                type string;
                dr:source util;
            }
            leaf wutil {
                type string;
                dr:source wutil;
            }
            leaf status {
                type string;
                dr:source status;
            }
            leaf schedcounter {
                type string;
                dr:source schedcounter;
            }
        }
    }
    dr:command-app "xmlproxyd";
    rpc juniper-netconf-get  {
        dr:command-top-of-output "/customFwddCpu";
        dr:command-full-name "drend juniper-netconf-get";
        dr:cli-command "show custom fwdd cpu";
        dr:command-help "default <get> rpc";
        output {
                container customFwddCpu {
                    dr:source "/customFwddCpu";
                    uses customFwddCpu;
            }
        }
    }
}
```

* dr:command-app should be “xmlproxyd"
* dr:command-top-of-output should be the root path (custom name)
* dr:cli-command is the cli operational command we execute to retrieve data 
* The output refers the yang grouping using the “uses” statement. We can also individually mention the container and leafs if needed. 

### Load the xmlproxy yang

You can load the yang using similar steps to above with a minor change 

request system yang add package custom-ipsec-xmlproxy proxy-xml module /tmp/xmlproxyd_customFwddCpu.yang

```
root@vsrx1> request system yang add package custom-ipsec-xmlproxy proxy-xml module /tmp/xmlproxyd_customFwddCpu.yang
XML proxy YANG module validation for xmlproxyd_customFwddCpu.yang : START
XML proxy YANG module validation for xmlproxyd_customFwddCpu.yang : SUCCESS
JSON generation for xmlproxyd_customFwddCpu.yang : START
JSON generation for xmlproxyd_customFwddCpu.yang : SUCCESS
```

#### Test the sensor using Jtimon

##### Download jtimon from GitHub and subscribe for the custom sensor to check if you receive the output.

Cd jtimon
make docker

```
docker build --build-arg COMMIT=1e5e4aa2db2a2a596ff9ac64fa42507eac641cb8 --build-arg BRANCH=master --build-arg TIME=2020-07-12T13:43:55-0400 -t jtimon .
Sending build context to Docker daemon  48.62MB
Step 1/12 : FROM golang:1.13.4-alpine3.10 as builder
1.13.4-alpine3.10: Pulling from library/golang
89d9c30c1d48: Pull complete
8ef94372a977: Pull complete
1ec62c064901: Pull complete
a47b1e89d194: Pull complete
bf1a3d234800: Pull complete
Digest: sha256:9d2a7c5b6447f525da0a4f18efd2cb05bf7d70228f75d713b7a67345f30157ac
Status: Downloaded newer image for golang:1.13.4-alpine3.10
 ---> 3024b4e742b0
Step 2/12 : ARG COMMIT
 ---> Running in 41fc9d27480b
Removing intermediate container 41fc9d27480b
 ---> 273908e20901
Step 3/12 : ARG BRANCH
 ---> Running in ae29366bc794
Removing intermediate container ae29366bc794
 ---> a1f0d4dffc87
Step 4/12 : ARG TIME
 ---> Running in 1e84178d9b2a
Removing intermediate container 1e84178d9b2a
 ---> db4be3cb3973
Step 5/12 : WORKDIR /go/src/app
 ---> Running in a3d54f4ae659
Removing intermediate container a3d54f4ae659
 ---> f9bc7caeecd6
Step 6/12 : COPY . .
 ---> b53c30355542
Step 7/12 : RUN GO111MODULE=on CGO_ENABLED=0 go build -mod vendor     --ldflags="-X main.jtimonVersion=${COMMIT}-${BRANCH} -X main.buildTime=${TIME}"     -o /usr/local/bin/jtimon
 ---> Running in e5e8067cbb17
Removing intermediate container e5e8067cbb17
 ---> 8e5b9c7386dd
Step 8/12 : FROM alpine
latest: Pulling from library/alpine
df20fa9351a1: Pull complete
Digest: sha256:185518070891758909c9f839cf4ca393ee977ac378609f700f60a771a2dfe321
Status: Downloaded newer image for alpine:latest
 ---> a24bb4013296
Step 9/12 : COPY --from=builder /usr/local/bin/jtimon /usr/local/bin/jtimon
 ---> 6bbcae8a6abd
Step 10/12 : VOLUME /u
 ---> Running in 33a005138358
Removing intermediate container 33a005138358
 ---> 8daa4c505eeb
Step 11/12 : WORKDIR /u
 ---> Running in 14e8c4221b4e
Removing intermediate container 14e8c4221b4e
 ---> 471db3ad2602
Step 12/12 : ENTRYPOINT ["/usr/local/bin/jtimon"]
 ---> Running in 2984dec902b9
Removing intermediate container 2984dec902b9
 ---> 132f9cea3567
Successfully built 132f9cea3567
Successfully tagged jtimon:latest
ln -sf launch-docker-container.sh jtimon
Usage: docker run -ti --rm jtimon --help
or simply call the shell script './jtimon --help
```

##### Create the configuration with custom sensor path 

You can use JTImon or any other tool which can subscribe directly over the sensor path as explained below. Or you can configure the resource and make it configurable on Junos such that the telemetry sensor can stream to a particular end point over a specific port. 

Enable gRPC on the Junos box using the below configuration

```
set system services extension-service request-response grpc clear-text port 32767
set system services extension-service notification allow-clients address 0.0.0.0/0
```

###### Test using JTImon

Create the Json configuration for Jtimon

Below is a minimum configuration to subscribe to a GRPC sensor 

```
{
    "host": "10.102.144.81",
    "port": 32767,
    "user": "root",
    "password": "juniper123",
    "cid": "script_cli",
    "paths": [{
        "path": "/customIpsecFwdd",
        "freq": 30000
    }],
    "log": {
        "file": "log.txt",
        "periodic-stats": 0,
        "verbose": false
    }
}
```

Subscribe using ./jtimon --print --config test_custom_sensor.json

###### Test using Junos configuration

Configure the below on Junos in case you do not want to subscribe using jtimon or any other tool.

###### Verify xmlproxyd working 

```
root@vsrx1> show agent sensors

Sensor Information :


    Name                                    : sensor_1005
    Resource                                : /customIpsecFwdd/
    Version                                 : 1.0
    Sensor-id                               : 539528118
    Subscription-ID                         : 1005
    Parent-Sensor-Name                      : Not applicable
    Component(s)                            : xmlproxyd


    Profile Information :


        Name                                : export_1005
        Reporting-interval                  : 3
        Payload-size                        : 5000
        Format                              : GPB
```

Once you Enable xmlproxyd in traceoptions, you can view the file as below and notice the output.

```
Jul 13 12:43:17 xmlproxy_telemetry_end_streaming: sensor /customFwddCpu/ result 1
Jul 13 12:43:17 synch_signal_handler processing signal received
Jul 13 12:45:36 asynch_signal_handler: signal received 31
Jul 13 12:45:36 synch_signal_handler processing signal received
Jul 13 12:45:37 xmlproxy_telemetry_start_streaming: sensor /customFwddCpu/
Jul 13 12:45:37 xmlproxy_build_context: command show custom fwdd cpu merge-tag:
Jul 13 12:45:37 <command format="xml">show custom fwdd cpu</command>
Jul 13 12:45:37 xmlproxy_execute_cli_command: Sent RPC...
Jul 13 12:45:44 xmlproxy_execute_cli_command: <customFwddCpu>
<cpu>
<util>
0
</util>
<status>
alive
</status>
<schedcounter>
521442
</schedcounter>
<wutil>
0
</wutil>
<cpu-num>
1
</cpu-num>
</cpu>
<cpu>
<util>
0
</util>
<status>
alive
</status>
<schedcounter>
521442
</schedcounter>
<wutil>
0
</wutil>
<cpu-num>
2
</cpu-num>
</cpu>
<cpu>
<util>
0
</util>
<status>
alive
</status>
<schedcounter>
521442
</schedcounter>
<wutil>
0
</wutil>
<cpu-num>
3
</cpu-num>
</cpu>
</customFwddCpu>
Jul 13 12:45:44
```

## References
* https://www.juniper.net/documentation/en_US/junos/topics/task/configuration/sensor-junos-telemetry-interface-configuring.html
* https://www.juniper.net/documentation/en_US/junos/topics/task/program/netconf-yang-scripts-action-creating.html
* https://www.juniper.net/documentation/en_US/junos/topics/task/program/netconf-yang-scripts-translation-creating.html
* https://forums.juniper.net/t5/Automation/Create-your-own-Telemetry-Sensor-in-Junos/ta-p/320493
* https://github.com/nileshsimaria/jtimon

