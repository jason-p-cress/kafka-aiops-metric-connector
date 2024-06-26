<h1>Kafka -> IBM AIOps connector for metrics</h1>

<h2>Summary:</h2>

   Reads data from a specified kafka topic, transforms the data using the specified transformer code
   and posts the resulting metrics to the IBM AIOps metrics API.

   Supports raw JSON or Avro format.

<h2>Requirements:</h2>

   Requires librdkafka libraries to be installed. If SSL connectivity is required, you may need to
   install openssl-devel and rebuild / reinstall librdkafka to include ssl support. The process is as
   follows:

      yum install openssl-devel gcc g++
      wget https://github.com/edenhill/librdkafka/archive/refs/tags/v1.6.2.zip 
      unzip v1.6.2
      cd librdkafka-1.6.2
      ./configure
      make
      make install


   If the SevOne kafka server and/or the Watson AIOps machines aren't dns resolvable, you may have to
   place entries in the /etc/hosts file on the server where this datachannel is run:

      Failed to resolve 'sevone-kafka:9092': Name or service not known 


<h2>Installing:</h2>

   From git: 

      1. git clone https://github.ibm.com/jcress/kafka-aiops-metric-connector

   From zip:

      1. download zip (Code -> Download ZIP)
      2. Create a directory for the data channel to reside (e.g. /opt/IBM/scanalytics/kafka-aiops-metric-connector)
      3. cd to created directory (e.g. cd /opt/IBM/scanalytics/kafka-aiops-metric-connector)
      4. unzip path/to/zip/kafka-aiops-metric-connector.zip


<h2>Configuring:</h2>

NOTE: if SevOne is placing metrics in Avro format, you must obtain the SevOne Avro schema from the
      SevOne Data Bus server. Replace the file 'config/avro-schema.json' with the schema
      obtained from SDB.

The properties file can be found at 'config/kafka-aiops-metric-connector.props'. The following properties
need to be configured:

	**sourceKafkaDataFormat** - either "Avro" or "JSON". Defaults to "Avro"
	**sourceKafkaTopicName** - the kafka topic name. Defaults to "sdb"
	**sourceKafkaServers** - one or more SDB kafka server:port combinations, separated by commas. Required.

	   e.g.:
	            sourceKafkaServers = "host1:9092,host2:9092"
	**transformerLibrary - the name of the library that transform the source JSON metric to the required PI or AIOps format.
                               The code libraries live under the <installationdir>/python/transformers/ directory.
	**sourceKafkaSSL** - set to 'true' if the Kafka server requires SSL. If true, then 
                         edit the config/source-kafka-ssl.props to include the CA and server certificates, 
                         and the key file.

        **watsonProductTarget** - will either be "pi" for Predictive Insights, or "aiops" for CloudPak for AIOps
	**publishType** - can be configured to publish to Predictive Insights REST mediation server's Kafka topic.
                          If this is desired, set to "kafka". Otherwise, use "rest"
	**watsonKafkaServers** - one or more Watson AIOops kafka servers for the PI mediation service, separated
	                     by commas. Required.
	**watsonKafkaTopicName** -  the topic name of the PI kafka. Defaults to 'metrics'. Do not change this unless
                                    you have a good reason.
	**watsonMetricGroup** - metric group name used when subitting metrics via rest. Defaults to 'sevone'. This
                                is used in the AIOps metric search UI
	**watsonTopicName** - the name of the Watson MAD topic that was created to ingest kafka/REST metrics
	                  in Predictive Insights, Metric Manager, or Watson MAD. Required.
	**watsonTopicAggInterval** - the aggregation interval of the Watson topic in minutes. Defaults to 5. Not
	                         strictly required to be set correctly, but will give accurate information
	                         regarding the number of metrics, resources, and indicators per topic 
	                         interval, which is useful for sizing.
	**watsonKafkaSSL** - set to 'true' if the Predictive Insights Kafka server requires SSL. If true, then edit the
                         config/watson-kafka-ssl.props to include the CA and server certificates, 
                         and the key file.

	**restMediationServiceHost** - if publishing to the Predictive Insights REST API, this is the host that is
                                       running the REST mediation service.
	**restMediationServicePort** - if publishing to the Predictive Insights REST API, this is the TCP port
	**logUniqueIndicators** - "true" or "false". If set to "true", every unique indicator name collected 
	                      per interval is logged in the datachannel log file. Useful to identify whether
	                      missing expected metrics are actually being received by the datachannel.
	**logUniqueResources** - "true" or "false". If set to "true", every unique resource collected per
	                     interval is logged in the datachannel log file.
	**logLevel** - For standard logging, set to "INFO". For additional/expanded logging set to "DEBUG"

If SSL communication is required for the source Kafka bus, you must edit the config/source-kafka-ssl.props to
include the CA and server certificates, and the key file.
 

<h2>Starting the connector:</h2>

      --Python script--

      The python code which is located under the <install location>/python directory. This code depends
      on the following python packages, which can be installed using the python package manager 'pip' as
      such:

         pip install fastavro
         pip install avro
         pip install confluent-kafka

      For general guidelines on how to install these dependencies, see the section below entitled 
      <b>"Installing python dependencies"</b>

      To start the datachannel using the python script, run:

         "nohup <install location>/python/kafka-aiops-metric-connector.py &"


<h2>Verifying that the datachannel is working:</h2>

   The included 'pi-kafka-reader' and 'pi-kafka-reader.py' components will connect to the configured Watson
   AIOps kafka topic and print out all messages hitting the topic. This is a quick and easy way to verify 
   that data is flowing from the source Kafka and to the Watson AIOps topic.

   The following log files are found under the "<install location>/log" directory:

      kafka-aiops-metrics-connector.log	- info, debug, and performance and data stats are found here
      datachannel.out		- initial startup log entries
      datachannel.err		- runtime errors (stderr)

<h2>Performance Monitoring</h2>

      Various performance statistics are logged to the '.log' file every Watson AIOps metric
      interval:

         Longest kafka latency for interval: This is the time it takes from collection, to the time
            that it is read off of the kafka topic. This should be as close to real-time as
            possible (within seconds). If this latency time is longer than twice the Watson AIOps
            aggregation interval, you will likely need to extend the latency of the WAIOps topic. For 
            example, if the WAIOps aggregation interval is 5 minutes (300 seconds), and the kafka read
            latency is topping out at 720 seconds, you should consider running the WAIOps topic at a 
            latency of a minimum of 2 minutes.

         Number of unique metric/resources consumed: The effective metric count for the last interval (that
            is, the number of kafka recoreds collected). This information can be useful for sizing the 
            WAIOps metric manager. This number should not vary much, unless SevOne has many different
            polling frequencies (e.g. 5 minutes for some metrics, 10 minues for other metrics).

         Number of uniqe metric indicators: This is the count of unique metric names collected in the last
            interval. Should be fairly consistent per interval unless poll times vary per metric/devices.

         Number of unique resources: The number of unique resources (e.g. router:interface, etc) seen 
            during the interval. Should be reasonably consistent per interval inless poll times vary per
            devices/device groups.

         PI Kafka producer queue length: This should be as close to '0' as possible. If you are seeing a
            high number, or the number is growing with each interval, this could indicate performance
            issues with either AIOps or the server running this connector.

     Indicator and resource logging:

        You can log unique instances of resources and/or indicators seen during each aggregation interval by
        enabling the extended logging options in the conf file:

           logUniqueIndicators = "true"
           logUniqueResources = "true"

        Depending on the size of your metric source counts, this can cause a high amount of disk utilization.
   
<h2>Installing python dependencies:</h2>

   <h3>Note:</h3>
   This is only required if you have a need to run the python code, rather than the self-contained binary.

   These are only high-level general steps, and may differ depending on your version and distribution of
   Linux.

   For RHEL 7 and Python 2.7.x (versions supported by PI REST mediation), ensure the following yum system 
   packages are available, and install them if not:

      yum install gcc
      yum install python-devel

   If not already installed, install the Python package manager 'pip'.
   Note that on RHEL 7.x and Python 2.7.x, pip is located in the EPEL
   repository. Enabling EPEL repository and installation of pip for python 2.7.x:

      sudo yum -y install epel-release

   If the above fails, an alternate method is to install epel-release from the fedora project using wget:

      wget https://dl.fedoraproject.org/pub/epel/epel-release-latest-7.noarch.rpm
      sudo yum -y install epel-release-latest-7.noarch.rpm

   Once the epel-release repo has been activated, install pip as such:

      sudo yum install python2-pip

   Once you have pip installed, install the following additional python setup packages:

      sudo pip install pip==20.3.4		upgrades pip
      sudo pip install setuputils
      sudo pip install -U setuputils		upgrades setuputils

   Install the python dependencies:

      sudo pip install confluent-kafka==1.5.0
      sudo pip install fastavro
      sudo pip install avro

   
   For other versions of Linux and python, the required pakages are generally the same, but the process
   may differ slightly. Consult your distribution's documentation for installing pip & setuputils, which 
   will allow you to install the three python dependencies.

