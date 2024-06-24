#!/usr/bin/python3.11

#
# Kafka to IBM AIOps connector for metric anomaly detection
#
# 04/01/22 - Jason Cress (jcress@us.ibm.com)
# 12/19/22 - Restructured the threading, added interrupt handler, added SSL support for SDB
#  4/20/23 - Fixed scope issues when using SSL certificates
#
# TODO:
#
# - sleep and retry when connection lost to either sdb or watson
#
#

import sys

#sys.path.append('./transformers/')
#from tlMeerkat import translateToWatsonMetric


import gzip
import urllib.request, urllib.parse, urllib.error 
import base64
from avro.io import DatumReader
#import avro.io
import logging
try: 
    import queue
except ImportError:
    import queue as queue
import socket
import ssl
import time
import threading
from datetime import datetime
try:
   from confluent_kafka import Consumer, KafkaError, Producer
except ImportError:
   print("FATAL: Unable to load confluent_kafka. Make sure you have installed confluent-kafka package. It can be installed using pip as such:\n\tpip install confluent-kafka")
   exit()
from confluent_kafka.admin import AdminClient
#from confluent_kafka.schema_registry.avro import AvroDeserializer
import io
import json
import os
import re
import time
import signal

def is_json(str):

   # This function tests whether a string is valid json or not. returns True or False
   try:
      json_object = json.loads(str)
   except ValueError as e:
      return False
   return True

def writeZipFile(fileName, metricData):

   gz = gzip.open(fileName + ".gz", 'wb')
   gz.write(metricData)
   gz.close()
   
def shutdownHandler(*args):
   shutdownRequest = True
   raise SystemExit('Exiting via user request')

def reconfigHandler(*args):
   logging.info("###############################################")
   logging.info("#                                             #")
   logging.info("# Re-reading datachannel configuration file.. #")
   logging.info("#                                             #")
   logging.info("###############################################")
   configProperties()
   
######################################################
#
# Function to load and validate datachannel properties
#
######################################################

def loadProperties(filepath, sep='=', comment_char='#'):

    # Read the file passed as parameter as a properties file.
    
    props = {}
    with open(filepath, "rt") as f:
        for line in f:
            l = line.strip()
            if l and not l.startswith(comment_char) and "=" in l:
                key_value = l.split(sep)
                key = key_value[0].strip()
                value = sep.join(key_value[1:]).strip().strip('"')
                props[key] = value

    return props

###############################################
#
# Function to read the metrics-ignore.conf file
#
###############################################

def loadMetricsIgnore(filepath, comment_char='#'):

   if(os.path.exists(filepath)):
      with open (filepath, "rt") as f:
         for line in f:
            l = line.strip()
            if l and not l.startswith(comment_char):
               ignoreMetrics.add(l)

###############################################
#
# Function to read the counter-metrics.conf file
#
###############################################

def loadCounters(filepath, comment_char='#'):

   if(os.path.exists(filepath)):
      with open (filepath, "rt") as f:
         for line in f:
            l = line.strip()
            if l and not l.startswith(comment_char):
               counterMetrics.add(l)

###################################
#
# Producer acknowledgement function
#
###################################

def acked(err,msg):
   if err is not None:
      logging.info("Failed to deliver message: %s: %s" % (str(msg), str(err)))
   else:
      pass
      #print("Message produced: %s" % (str(msg)))

#####################################
#
# Puts metric onto Watson kafka topic
#
#####################################

def produceMetric(metricData):

   watsonProducer.produce(watsonKafkaTopicName,key="key",value=metricData, callback=acked)
   watsonProducer.poll(0.001)

def postMetric(postedData):

   # accepts a JSON payload and posts it to watson

   retryCount = 4

   if 1 == 1: 

      #global restMediationServiceHost
      #global restMediationServicePort
      #global watsonTopicName
      #global restMediationServiceAuthentication
   
      #encodedMetricData = metricData.encode('utf-8')
      encodedMetricData = postedData.encode('utf-8')
   
      #logging.debug("going to publish the following: " + str(encodedMetricData))
      #######################################################
      #
      # Function to post metric to WAIOps for analysis
      #
      #######################################################
   
      doRetry = True
      retries = 1
   
      method = "POST"
   
      logging.debug("requestURL is " + targetUrl + ", now going to post")

      while doRetry == True:
         try:
            request = urllib.request.Request(targetUrl, data=encodedMetricData)
            request.add_header("Content-Type",'application/json')
            if(watsonProductTarget == "pi"):
               request.add_header("X-TenantID",watsonTopicName)
            logging.debug("setting authentication header, if required")
            if(restMediationServiceAuthentication.lower() == "true"):
               request.add_header("Authorization",authHeader)
            if(watsonProductTarget == "aiops"):
               request.add_header("X-TenantID",watsonTenantId)
               request.add_header("Authorization", "ZenApiKey ".encode("utf-8") + zenApiKey)
            logging.debug("Posting with headers: " + str(request.headers))
            request.get_method = lambda: method
            response = urllib.request.urlopen(request)
            doRetry = False
      
         except IOError as e:
            logging.info('Failed to open "%s".' % targetUrl)
            if hasattr(e, 'code'):
               logging.info('We failed with error code - %s.' % e.code)
            if hasattr(e, 'reason'):
               logging.info("The error object has the following 'reason' attribute :")
               logging.info(e.reason)

            if retries != retryCount:
               retries = retries + 1
               logging.info("going to retry, sleeping for " + str(retries * 3) + " seconds...")
               time.sleep(retries * 3) 
            else:
               logging.info("max retries reached for metric post, saving to file and continuing...")
               savFileName = mediatorHome + "/log/metricsave__" + datetime.now().strftime("%Y-%m-%d_%H:%M:%S") + ".json"
               writeZipFile(savFileName, encodedMetricData)
               #wrz = threading.Thread(target=writeZipFile, args=(savFileName, encodedMetricData), kwargs={})
               #wrz.start()
               #savFile = open(mediatorHome + "/log/metricsave__" + currTime + ".json", "w")
               #savFile.write(encodedMetricData)
               doRetry = False 



def logTimeDelta(first):

   global watsonTopicAggInterval
   global longestDelta
   global intervalMetricCount
   global shutdownRequest

   ###############################################################
   #
   # This function runs every PI interval (5-minutes), and logs
   # out the following information:
   #
   #   - Average kafka latency (seconds)
   #   - Longest kafka latency (seconds)
   # 
   #   These metrics show the average/longest time it takes from
   #    collection time to the time in which we pick it
   #   up from the kafka topic. 
   #
   #   - Number of metrics consumed (count)
   #
   #   The number of metrics collected during the interval. This
   #   count should be reasonably consistent every interval. 
   #   
   #   - PI Kafka producer queue length (count)
   #
   #   The number of metrics waiting to be sent to the AIOps
   #   api. If this number is large (i.e. > 100) and/or
   #   continues to grow larger with every interval, then it is 
   #   may be due to performance issues with this script, or 
   #   problems AIOps is experiencing in handling the metric load
   # 
   #
   ###############################################################

   while shutdownRequest != True:
      if first:
         secToInterval = (( 4 - datetime.now().minute % int(watsonTopicAggInterval)) * 60 ) + (60 - datetime.now().second)
         logging.info("Starting datachannel, " + str(secToInterval) + " seconds to next interval...")
         time.sleep(secToInterval)
      currTime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
      first=False
      logging.info('==== INTERVAL STATISTICS FOR ' + currTime + '====')
      ###############################################
      #
      # If indicator/resource logging is requested...
      #
      ###############################################
      if(logUniqueIndicators.lower() == "true"):
         logging.debug('Unique indicators seen during interval: ' + str(intervalMetricSet))
      if(logUniqueResources.lower() == "true"):
         logging.debug('Unique resources seen during interval: ' + str(intervalResourceSet))
      logging.info('Longest kafka latency for interval is: ' + str(longestDelta / 1000) + ' seconds.')
      logging.info('Number of unique metric/resources consumed (metric count): ' + str(intervalMetricCount) )
      logging.info('Number of unique metric indicators: ' + str(len(intervalMetricSet)))
      logging.info('Number of unique resources: ' + str(len(intervalResourceSet)))
      logging.info('Datachannel producer queue length: ' + str(publishQueue.qsize()))
      #logging.info('Datachannel publisher metric group size: ' + str(len(restMetricGroup["groups"])))
      #if(publishType.lower() == "rest" or publishType.lower() == "file"):
      if("rest" in publishTypes or "file" in publishTypes ):
         logging.info('Size of metricGroup now: ' + str(len(restMetricGroup["groups"] )))
      intervalMetricSet.clear()
      intervalResourceSet.clear()
      intervalMetricCount = 0
      longestDelta = 0
      time.sleep(int(watsonTopicAggInterval) * 60)

def logTimeDeltaCron(callback_func, first=True):

   #################################################################
   #
   # Sets up a "cron" type job that logs perf stats every 60 seconds
   #
   #################################################################
   
   if first:
      secToInterval = (( 4 - datetime.now().minute % int(watsonTopicAggInterval)) * 60 ) + (60 - datetime.now().second)
      time.sleep(secToInterval)
   callback_func()
   time.sleep(int(watsonTopicAggInterval) * 60)
   logTimeDeltaCron(callback_func, False)


def fastAvroDecode(msg_value):

   #############################################################################################
   #
   # This function decodes the avro message, and returns a python dictionary structure
   #
   #############################################################################################

   message_bytes = io.BytesIO(msg_value)
   event_dict = fastavro.schemaless_reader(message_bytes, fastavro.parse_schema(schema))
   return event_dict

def writeRawJson(rawJson):

   jsonLogFileLocation.write(json.dumps(rawJson, indent=4) + "\n") 

def kafkaQueueReader():

   ###########################
   #
   # Publisher thread function
   #
   ###########################

   global shutdownRequest

   # block until a message hits the publish queue

   while shutdownRequest != True:
      item = publishQueue.get()
      produceMetric(json.dumps(item))
      if(logRawJson):
         writeRawJson(json.dumps(item))
      publishQueue.task_done()

def publishQueueReader():

   global shutdownRequest
   global publishTypes
   restBatchSize = 50000
   filePublishFrequency = 300

   global restMetricGroup 

   restMetricGroup = {}
   restMetricGroup["groups"] = []

   # block until a message hits the publish queue

   logging.info("Starting queue reader for publishing")
   lastPublishTime = int(time.time())
   while shutdownRequest != True:
      # block until a message hits the publishQueue
      item = publishQueue.get()
      #print("got an item: " + json.dumps(item, indent=4))
      for metric in item["groups"]:
         #print("metric: " + str(metric))
         restMetricGroup["groups"].append(metric)
      if(len(restMetricGroup["groups"]) == restBatchSize and publishType == "rest"):
         logging.debug("publishing batch of " + str(restBatchSize))
         for publishType in publishTypes:
            if(publishType.lower() == "rest"):
               postMetric(json.dumps(restMetricGroup))
            if(publishType.lower() == "file"):
               savFileName = mediatorHome + "/log/metricsave__" + datetime.now().strftime("%Y-%m-%d_%H:%M:%S") + ".json"
               encodedMetricData = json.dumps(restMetricGroup).encode('utf-8')
               writeZipFile(savFileName, encodedMetricData)
         restMetricGroup.clear()
         restMetricGroup["groups"] = []
         lastPublishTime = int(time.time())
      elif( int(time.time()) - lastPublishTime > filePublishFrequency  and len(restMetricGroup["groups"]) > 0 and publishType.lower() == "file" ):
         logging.debug("publishing " + str(len(restMetricGroup["groups"])) + " metrics on filePublishFrequency of " + str(filePublishFrequency))
         for publishType in publishTypes:
            if(publishType.lower == "rest"):
               postMetric(json.dumps(restMetricGroup))
            if(publishType.lower == "file"):
               savFileName = mediatorHome + "/log/metricsave__" + datetime.now().strftime("%Y-%m-%d_%H:%M:%S") + ".json"
               encodedMetricData = json.dumps(restMetricGroup).encode('utf-8')
               writeZipFile(savFileName, encodedMetricData)
         restMetricGroup.clear()
         restMetricGroup["groups"] = []
         lastPublishTime = int(time.time())
      else:
         pass
   publishQueue.task_done()


def kafkaReader():

   ########################################
   #
   # Kafka reader thread function
   #
   ########################################

    global intervalMetricCount
    global longestDelta

    shutdownRequest = False
    lastMessage = "NULL"
#    try:
    if(1==1):
        while shutdownRequest != True:
            msg = c.poll(1)
            if msg is None:
                continue
            elif not msg.error():
               if sourceKafkaDataFormat.lower() == "avro":
                  try:
                     metricJson = transformerModule.translateToWatsonMetric(fastAvroDecode(msg.value()),  ignoreMetrics, counterMetrics, watsonMetricGroup )
                  except Exception as error:
                     logging.info("An exception occurred in transformation of kafka JSON payload: " + str(error))
                     logging.info("JSON payload received from kafka: " + fastAvroDecode(msg.value()))
               else:
                  #lines = format(msg.value()).splitlines()
                  lines = msg.value().splitlines()
                  for line in lines:
                     if is_json(line):
                        metric = json.loads(line)
                     else:
                        logging.info("String received is not a valid JSON. Received: " + str(line))
                     logging.debug("transforming " + str(metric))
                     try:
                        metricJson = transformerModule.translateToWatsonMetric(json.loads(line),  ignoreMetrics, counterMetrics, watsonMetricGroup)
                        #logging.debug("Going to post the following JSON to AIOps: " + json.dumps(metricJson))
                     except Exception as error:
                        logging.info("An exception occurred in transformation of the following kafka JSON payload: " + str(line))
                        #logging.info("JSON payload received from kafka: " + json.dumps(line))
                     lastMessage = metricJson
                     if("error" in metricJson):
                        if metricJson["error"] != "ignore":
                           logging.info(metricJson["error"])
                        #pass
                     else:
                        #print(metricJson)
                        # No error received during transformation, continue to publish
                        if 'timestamp' in metricJson["groups"][0]:
                           # Technically this shouldn't happen...
                           #logging.info("good metric found: " + json.dumps(metricJson))
                           for key, value in metricJson["groups"][0]["metrics"].items():
                              # NaN values are not acceptable in MAD, and will cause an error if trying to publish...
                              # Normalize metrics if NaN value
                              #logging.info("Found metric:")
                              #logging.info(key, 'corresponds to', metricJson["groups"][0]["metrics"][key])
                              #logging.info(key + ":" + str(value))
                              if value != value:
                                 logging.debug("NaN value found, setting NaN value to zero")
                                 metricJson["groups"][0]["metrics"][key] = int(0)
                           logging.debug("Going to post the following JSON to AIOps: " + json.dumps(metricJson))
                           publishQueue.put(metricJson)
                           # Let's track some useful performance metrics...
                           intervalMetricCount += 1
                           currTime = int(time.time() * 1000)
                           deltaTime = currTime - int(metricJson["groups"][0]["timestamp"])
                           if(deltaTime > longestDelta):
                              longestDelta = deltaTime
                           for key in metricJson["groups"][0]["metrics"]:
                              intervalMetricSet.add(key)
                           if 'resourceID' in metricJson["groups"][0]:
                              intervalResourceSet.add(metricJson["groups"][0]["resourceID"])
                        else:
                           logging.info("WARNING: Message received contains no timestamp field. Message is: " + json.dumps(metricJson))
                
            elif msg.error().code() == KafkaError._PARTITION_EOF:
                logging.info('Kafka error: end of partition reached')
                #logging.info('Kafka error: end of partition reached {0}/{1}'
                #      .format(msg.topic(), msg.partition()))
            else:
                #logging.info('Kafka error occured: {0}'.format(msg.error().str()))
                logging.info('Kafka error occured: ' + str(msg.error().code()))
    
#    except Exception as error:
#       logging.info("An exception occurred: " + str(error))
#       #shutdownRequest = True
#       now = datetime.now()
#       ts = now.strftime("%d/%m/%Y %H-%M-%S")
#       #logging.info('Mediator shut down at: ' + ts)
#       logging.info('Mediator continuing after error at: ' + ts)
#       if(lastMessage):
#          logging.info('Last message: ' + json.dumps(lastMessage))
#       if(publishThread.is_alive()):
#          logging.debug("publishThread is still alive")
#       if(perfStatThread.is_alive()):
#          logging.debug("perfStatThread is still alive")
#       #c.close()
#       #sys.stdout.close()

def setupFilePaths():
   
   ###################
   #
   # Set up file paths
   #
   ###################
   
   # The following does not work if using nuitka to compile the code into ELF binary. Using sys.argv[0] instead
   
   #mediatorBinDir = os.path.dirname(os.path.abspath(__file__))

   global mediatorHome
   global mediatorBinDir
   
   #print('sys.argv[0] =', sys.argv[0])             
   pathname = os.path.dirname(sys.argv[0])        
   #print('path =', pathname)
   mediatorBinDir = os.path.abspath(pathname) + "/" + sys.argv[0]
   
   mediatorHome = os.path.dirname(os.path.abspath(pathname))
   
   print(("mediatorBinDir is: " + mediatorBinDir))
   
   print(("mediatorHome is: " + mediatorHome))
   
def setupLogging():

   ################
   #
   # Set up logging
   #
   ################

   
   if(os.path.isdir(mediatorHome + "/log")):
      logHome = mediatorHome + "/log/"
   
      # Redirect stdout to log/datachannel.out

      print(("Redirecting stdout to " + logHome + "datachannel.out"))
      print(("Redirecting stderr to " + logHome + "datachannel.err"))
      sys.stdout = open(logHome + "datachannel.out", "w")
      sys.stderr = open(logHome + "datachannel.err", "w")
      LOG_FILENAME=logHome + "kafka-aiops-connector.log"
      now = datetime.now()
      ts = now.strftime("%d/%m/%Y %H:%M:%S")
      print(("opening log file " + logHome + "/kafka-aiops-connector.log"))
      try:
         if loggingLevel.upper() == "INFO" or loggingLevel.upper() == "DEBUG":
            if loggingLevel.upper() == "INFO":
               logging.basicConfig(level=logging.INFO, filename=LOG_FILENAME, filemode="w+",format="%(asctime)-15s %(levelname)-8s %(message)s")
            else:
               logging.basicConfig(level=logging.DEBUG, filename=LOG_FILENAME, filemode="w+",format="%(asctime)-15s %(levelname)-8s %(message)s")
         else:
            logging.info("WARNING: Unknown loggingLevel specified in kafka-aiops-metric-connector.props. Must be one of 'INFO' or 'DEBUG'. Defaulting to 'INFO'")
         logging.info("Mediator started at: " + ts + "\n")
      except:
         print("FATAL: failed to start logging. Verify logging path available and disk space.")
         exit()
   else:
      print(("FATAL: unable to find log directory at " + mediatorHome + "log"))
      sys.exit()

def configProperties():

   ##########################################
   #
   # Read and validate datachannel properties
   # Include 'avro' packages if required
   #
   ##########################################
   
   global ignoreMetrics
   global counterMetrics
   global sourceKafkaServers
   global watsonKafkaServers
   global watsonTopicAggInterval
   global watsonKafkaTopicName
   global sourceKafkaTopicName
   global logUniqueIndicators
   global logUniqueResources
   global watsonProductTarget
   global datachannelProps
   global sourceKafkaDataFormat
   global restMediationServiceAuthentication
   global authHeader
   global targetUrl
   
   ignoreMetrics = set()
   loadMetricsIgnore(mediatorHome + "/conf/metrics-ignore.conf")
   counterMetrics = set()
   loadCounters(mediatorHome + "/conf/counter-metrics.conf")
   
   if(os.path.exists(mediatorHome + "/conf/kafka-aiops-metric-connector.props")):
      props = loadProperties(mediatorHome + "/conf/kafka-aiops-metric-connector.props")
   else:
      print(("FATAL: Properties file " + mediatorHome + "/conf/kafka-aiops-metric-connector.props is missing."))
      exit()
   
   # convert properties to variables
   
   globals().update(props)
   datachannelProps = (props)
   globals().update(datachannelProps)

   
   # configure logging based on level requested

   setupLogging()

   logging.info("Metrics to be ignored: ")
   for metric in ignoreMetrics:
      logging.info(metric)
   
   logging.info("Counter/pegged metrics: ")
   for metric in counterMetrics:
      logging.info(metric)
   
   # validate required properties exist and set defaults where possible
   
   logging.debug("Global variables:" + str(globals()))
   logging.debug("datachannelProps: " + str(datachannelProps))


   # Ensure that one or more Kafka servers are defined

   if 'sourceKafkaServers' not in datachannelProps:
      print("FATAL: sourceKafkaServers not set in properties file! Specify at least one Kafka server.")
      logging.info("FATAL: sourceKafkaServers not set in properties file! Specify at least one Kafka server.")
      exit()
   else:
      sourceKafkaServers = datachannelProps['sourceKafkaServers']
      logging.debug("sourceKafkaServers = " + str(sourceKafkaServers))
   
   global publishTypes
   publishTypes = []
   if( "publisherTypes" in globals()):
      publishers = datachannelProps["publisherTypes"].split(",")
      for publisher in publishers:
         if publisher.lower() in [ "kafka", "rest", "file" ]:
            if "watsonProductTarget" in globals():
               if(watsonProductTarget.lower() == "pi" and publisher.lower() == "rest"):
                  if( restMediationServiceProtocol.lower() in [ "http", "https" ] ):
                     if( "restMediationServicePort" in globals() and "restMediationServiceHost" in globals()):
                        targetUrl = restMediationServiceProtocol + '://' + restMediationServiceHost + ':' + restMediationServicePort + '/metrics/api/1.0/metrics'
                     else:
                        logging.info("FATAL: restMediationServicePort and/or restMediationServiceHost properties missing. Please configure these properties for PI rest mediation")
                        exit()
                  else:
                     logging.info("FATAL: Unknown restMediationServiceProtocol configured. Must be \'http\' or \'https\'")
                     exit()
                  if 'restMediationServiceAuthentication' in datachannelProps:
                     restMediationServiceAuthentication = datachannelProps['restMediationServiceAuthentication']
                     logging.debug("restMediationServiceAuthentication is " + restMediationServiceAuthentication)
                     if(restMediationServiceAuthentication.lower() == "true"):
                        logging.debug("REST authentication required")
                        if('restMediationServiceUsername' in datachannelProps and 'restMediationServicePassword' in datachannelProps):
                           restMediationServiceUsername = datachannelProps['restMediationServiceUsername'].encode("utf-8")
                           restMediationServicePassword = datachannelProps['restMediationServicePassword'].encode("utf-8")
                           authHeader = 'Basic '.encode("utf-8") + base64.b64encode(restMediationServiceUsername + ":".encode("utf-8") + restMediationServicePassword)
                           logging.debug("Auth header is: " + authHeader.decode("ascii"))
                        else:
                           logging.debug("REST mediation authentication requested, but missing restMediationServiceUsername | restMediationServicePassword in the config file")
                           exit()
                  else:
                     logging.info("Did not find restMediationServiceAuthentication property in configuration. Not requestiong authentication")
                     restMediationServiceAuthentication = "false"

               if(watsonProductTarget.lower() == "aiops" and publisher.lower() == "kafka"):
                  logging.info("FATAL: publishType is set to \'kafka'\, but watsonProductTarget is \'aiops\'. This is an unsupported configuration. For watsonProductTarget of \'aiops\' you must use \'rest\' and/or \'file\'")
                  exit()
            else:
               logging.info("FATAL: watsonProductTarget not set. Must be \'aiops\' or \'pi\'")
               exit()
            publishTypes.append(publisher)
         else:
            logging.info("WARNING: unknown publisher type (" + publisher + ") defined in publisherTypes configuration. Must be one of 'kafka', 'rest', or 'file'")
      if( len(publishTypes) == 0 ):
         logging.info("FATAL: No valid publisherTypes were defined in configuration file. Must be 'kafka', 'rest', or 'file'")

   else: 
      logging.info("FATAL: publisherTypes not set in kafka-aiops-metric-connector.props. Please set to one or more of 'kafka', 'rest', or 'file'")
      exit()

   # Ensure that one or more Watson AIOps Kafka servers are defined

      if 'watsonKafkaServers' not in datachannelProps:
         print("FATAL: watsonKafkaServers not set in properties file! Specify at least one Watson AIOps kafka server.")
         logging.info("FATAL: watsonKafkaServers not set in properties file! Specify at least one Watson AIOps kafka server.")
         exit()
      else: 
         logging.debug("Setting watsonKafkaServers to " + str(props['watsonKafkaServers']))
         watsonKafkaServers = datachannelProps['watsonKafkaServers']
         logging.debug("watsonKafkaServers: " + str(watsonKafkaServers))
      
      # Ensure that the Watson AIOps Kafka topic name has been configured
   
      if 'watsonKafkaTopicName' not in datachannelProps:
         print("FATAL: Watson AIOps kafka topic name not specified in properties file! Configure the topic name property \"watsonKafkaTopicName\"")
         logging.info("FATAL: Watson AIOps kafka topic name not specified in properties file! Configure the topic name property \"watsonKafkaTopicName\"")
         logging.info("The properties are: " + str(globals()))
         exit()
      else:
         logging.debug("Setting watsonKafkaTopicName to " + str(props['watsonKafkaTopicName']))
         watsonKafkaTopicName = datachannelProps['watsonKafkaTopicName']
         logging.debug("watsonKafkaTopicName = " + str(watsonKafkaTopicName))

      # Determine whether SSL communication is required for the Watson Kafka broker(s)
   
      if 'watsonKafkaSSL' in datachannelProps:
         watsonKafkaSSL = datachannelProps['watsonKafkaSSL'].lower()
         if watsonKafkaSSL.lower() == "true" or watsonKafkaSSL.lower() == "false":
            watsonKafkaSSL = datachannelProps['watsonKafkaSSL'].lower()
         else:
            logging.info("WARNING: Unknown 'watsonKafkaSSL' property set. Should be \"true\" or \"false\". Defaulting to \"false\"")
            watsonKafkaSSL = "false"
      else:
         logging.info("watsonKafkaSSL not set in props file. Defaulting to \"false\"")
         watsonKafkaSSL = "false"
   
      # configure SSL for Watson Kafka, if required
   
      if watsonKafkaSSL == "true":
         if(os.path.exists(mediatorHome + "/conf/watson-kafka-ssl.props")):
            watsonKafkaSSLProps = loadProperties(mediatorHome + "/conf/watson-kafka-ssl.props")
            logging.debug("Source Kafka SSL Properties: = " + json.dumps(watsonKafkaSSLProps))
            globals().update(watsonKafkaSSLProps)
            if(os.path.exists(watsonSSLCaLocation)):
               logging.debug("Watson Kafka SSL CA PEM file located at " + watsonSSLCaLocation)
            else:
               logging.info("FATAL: Watson Kafka SSL requested, but root CA file not found at " + watsonSSLCaLocation)
               exit()
            if(os.path.exists(watsonSSLCertificateLocation)):
               logging.debug("Watson Kafka SSL server certificate file located at " + watsonSSLCertificateLocation)
            else:
               logging.info("FATAL: Watson Kafka SSL requested, but server certificate file not found at " + watsonSSLCertificateLocation)
               exit()
            if(os.path.exists(watsonSSLKeyLocation)):
               logging.debug("Watson Kafka SSL key file located at " + watsonSSLKeyLocation)
            else:
               logging.info("FATAL: Watson Kafka SSL requested, but SSL key file not found at " + watsonSSLCertificateLocation)
               exit()
         else:
            print(("FATAL: Watson Kafka SSL set to true, but Watson Kafka SSL properties file " + mediatorHome + "/conf/watson-kafka-ssl.props is missing."))
            logging.info("FATAL: Properties file " + mediatorHome + "/conf/watson-kafka-ssl.props is missing.")
            exit()
      else:
         logging.info("Watson Data Bus Kafka SSL not requested")


      #restMetricGroup = {}

      #restMetricGroup["groups"] = []
   
   # Configure the aggregation interval, default and minimum 5

   if 'watsonTopicAggInterval' not in datachannelProps:
      watsonTopicAggInterval = "5"
      logging.info("watsonTopicAggInterval not specified in properties file. Setting to 5 minutes")
   else:
      watsonTopicAggInterval = datachannelProps['watsonTopicAggInterval']
      logging.debug("watsonTopicAggInterval = " + watsonTopicAggInterval)
   
   # Verify the Kafka topic name

   if 'sourceKafkaTopicName' not in datachannelProps:
      sourceKafkaTopicName = "sdb"
      logging.info("sourceKafkaTopicName not specified in properties file. Defaulting to \"sdb\".")
   else:
      sourceKafkaTopicName = datachannelProps['sourceKafkaTopicName']
   logging.debug("sourceKafkaTopicName = " + sourceKafkaTopicName)

   # Determine what IBM product this will integrate with, either the legacy Predictive Insights, or the Metric Anomaly Detection in either NOI or Watson AIOps AI Manager

   if 'watsonProductTarget' in datachannelProps:
      if(datachannelProps['watsonProductTarget'] == "aiops" or datachannelProps['watsonProductTarget'] == "pi"):   
         watsonProductTarget = datachannelProps['watsonProductTarget']
         logging.debug("datachannel product target is: " + watsonProductTarget)
      else:
         logging.info("FATAL: Property 'watsonProductTarget' unknown, should be \"pi\" or \"aiops\", it is configured as: " + watsonProductTarget['watsonProductTarget'])
         exit()
   else:
      logging.info("FATAL: Datachannel property 'watsonProductTarget' is not set, must be set to either \"pi\" for Predictive Insights, or \"aiops\" for NOI/WatsonAIOps")
      exit()

   # valiate required properties for a watsonProductTarget of "aiops"
   
   if watsonProductTarget == "aiops":
      if 'watsonTenantId' in datachannelProps:
         watsonTenantId = datachannelProps['watsonTenantId']
         logging.debug("AIOps tenant id is: " + watsonTenantId)
         if(watsonTenantId != "cfd95b7e-3bc7-4006-a4a8-a73a79c71255"):
            logging.info("WARNING: Watson/AIOps TenantId is not the default TenantId")
      else:
         logging.info("NOTE: datachannel property \'watsonTenantId\' is missing in the configuration file. Using default")
         watsonTenantId = "cfd95b7e-3bc7-4006-a4a8-a73a79c71255"
      
      if 'watsonRestRoute' in datachannelProps:
         watsonRestRoute = datachannelProps['watsonRestRoute'] 
         targetUrl = watsonRestRoute
      else:
         logging.info("FATAL: watsonRestRoute not configured in datachannel properties file. Add the property should be in the form: https://myOpenshiftDNSName/aiops/api/app/metric-api/v1/metrics")
         exit()

      if 'watsonApiKey' in datachannelProps:
         watsonApiKey = datachannelProps['watsonApiKey']
      else:
         logging.info("FATAL: watsonApiKey not configured in datachannel properties file. Create an API Key and configure the watsonApiKey property")
         exit()

      if 'watsonUser' in datachannelProps:
         watsonUser = datachannelProps['watsonUser']
      else:
         logging.info("FATAL: watsonUser is not configured in datachannel properties file. Create an API Key and configure the watsonUser property")
         exit()
      
      global zenApiKey

      zenApiKey = base64.b64encode(watsonUser.encode("utf-8") + ":".encode("utf-8") + watsonApiKey.encode("utf-8"))

#   # Determine whether SSL communication is required for the Watson Kafka broker(s)
#
#   if 'watsonKafkaSSL' in datachannelProps:
#      watsonKafkaSSL = datachannelProps['watsonKafkaSSL'].lower()
#      if watsonKafkaSSL.lower() == "true" or watsonKafkaSSL.lower() == "false":
#         watsonKafkaSSL = datachannelProps['watsonKafkaSSL'].lower()
#      else:
#         logging.info("WARNING: Unknown 'watsonKafkaSSL' property set. Should be \"true\" or \"false\". Defaulting to \"false\"")
#         watsonKafkaSSL = "false"
#   else:
#      logging.info("watsonKafkaSSL not set in props file. Defaulting to \"false\"")
#      watsonKafkaSSL = "false"
#
#   # configure SSL for Watson Kafka, if required
#
#   if watsonKafkaSSL == "true":
#      if(os.path.exists(mediatorHome + "/conf/sevone-kafka-ssl.props")):
#         watsonKafkaSSLProps = loadProperties(mediatorHome + "/conf/watson-kafka-ssl.props")
#         logging.debug("SevOne Kafka SSL Properties: = " + json.dumps(watsonKafkaSSLProps))
#         globals().update(watsonKafkaSSLProps)
#         if(os.path.exists(watsonSSLCaLocation)):
#            logging.debug("Watson Kafka SSL CA PEM file located at " + watsonSSLCaLocation)
#         else:
#            logging.info("FATAL: Watson Kafka SSL requested, but root CA file not found at " + watsonSSLCaLocation)
#            exit()
#         if(os.path.exists(watsonSSLCertificateLocation)):
#            logging.debug("Watson Kafka SSL server certificate file located at " + watsonSSLCertificateLocation)
#         else:
#            logging.info("FATAL: Watson Kafka SSL requested, but server certificate file not found at " + watsonSSLCertificateLocation)
#            exit()
#         if(os.path.exists(watsonSSLKeyLocation)):
#            logging.debug("Watson Kafka SSL key file located at " + watsonSSLKeyLocation)
#         else:
#            logging.info("FATAL: Watson Kafka SSL requested, but SSL key file not found at " + watsonSSLCertificateLocation)
#            exit()
#      else:
#         print("FATAL: Watson Kafka SSL set to true, but Watson Kafka SSL properties file " + mediatorHome + "/conf/watson-kafka-ssl.props is missing.")
#         logging.info("FATAL: Properties file " + mediatorHome + "/conf/watson-kafka-ssl.props is missing.")
#         exit()
#   else:
#      logging.info("Watson Data Bus Kafka SSL not requested")

   # Determine whether SSL communication is required for the Kafka broker(s)

   if 'sourceKafkaSSL' in datachannelProps:
      sourceKafkaSSL = datachannelProps['sourceKafkaSSL'].lower()
      if sourceKafkaSSL.lower() == "true" or sourceKafkaSSL.lower() == "false":
         sourceKafkaSSL = datachannelProps['sourceKafkaSSL'].lower()
      else:
         logging.info("WARNING: Unknown 'sourceKafkaSSL' property set. Should be \"true\" or \"false\". Defaulting to \"false\"")
         sourceKafkaSSL = "false"
   else:
      logging.info("sourceKafkaSSL not set in props file. Defaulting to \"false\"")
      sourceKafkaSSL = "false"

   # configure SSL for Kafka, if required

   if sourceKafkaSSL == "true":
      if(os.path.exists(mediatorHome + "/conf/source-kafka-ssl.props")):
         sourceKafkaSSLProps = loadProperties(mediatorHome + "/conf/source-kafka-ssl.props")
         logging.debug("Kafka SSL Properties: = " + json.dumps(sourceKafkaSSLProps))
         globals().update(sourceKafkaSSLProps)
         if(os.path.exists(sourceSSLCaLocation)):
            logging.debug("Kafka SSL CA PEM file located at " + sourceSSLCaLocation)
         else:
            logging.info("FATAL: Source Kafka SSL requested, but root CA file not found at " + sourceSSLCaLocation)
            exit()
         if(os.path.exists(sourceSSLCertificateLocation)):
            logging.debug("Source Kafka SSL server certificate file located at " + sourceSSLCertificateLocation)
         else:
            logging.info("FATAL: Source Kafka SSL requested, but server certificate file not found at " + sourceSSLCertificateLocation)
            exit()
         if(os.path.exists(sourceSSLKeyLocation)):
            logging.debug("Source Kafka SSL key file located at " + sourceSSLKeyLocation)
         else:
            logging.info("FATAL: Source Kafka SSL requested, but SSL key file not found at " + sourceSSLCertificateLocation)
            exit()
      else:
         print(("FATAL: Source Kafka SSL set to true, but source Kafka SSL properties file " + mediatorHome + "/conf/source-kafka-ssl.props is missing."))
         logging.info("FATAL: Properties file " + mediatorHome + "/conf/source-kafka-ssl.props is missing.")
         exit()
   else:
      logging.info("Source Kafka SSL not requested")
   
#############
#
# Begins here
#
#############

setupFilePaths()
configProperties()

global ignoreMetrics
global counterMetrics
global sourceKafkaServers
global watsonKafkaServers
global watsonTopicAggInterval
global watstonKafkaTopicName
global targetUrl


print("Starting datachannel")

shutdownRequest = False
intervalMetricSet = set()
intervalResourceSet = set()
longestDelta = 0
intervalNumber = 0
intervalMetricCount = 0


if 'sourceKafkaDataFormat' in datachannelProps:
   sourceKafkaDataFormat = datachannelProps['sourceKafkaDataFormat'] 
   if sourceKafkaDataFormat.lower() == "avro":
      try:
         import fastavro
      except ImportError:
         print("FATAL: Unable to load required Python package 'fastavro'. It can be installed using pip as such:\n\tpip install fastavro\n")
         exit()
      try:
         #import avro.io
         import avro.schema
      except ImportError:
         print("FATAL: Unable to load required Python package 'avro'. It can be installed using pip as such:\n\tpip install avro\n")
         exit()
   elif sourceKafkaDataFormat.lower() != "json":
      logging.info("Unknown sourceKafkaDataFormat value. Should be set to \"Avro\" or \"JSON\". Defaulting to \"Avro\".")
else:
   logging.info("sourceKafkaDataFormat not specified in properties file. Setting to \"Avro\".")
   sourceKafkaDataFormat = "Avro"
logging.debug("sourceKafkaDataFormat = " + sourceKafkaDataFormat)

# Configure statistical logging for the data channel

if 'logUniqueIndicators' not in datachannelProps:
   logUniqueIndicators = "false"
else:
   if datachannelProps['logUniqueIndicators'] != "false" or datachannelProps['logUniqueIndicators'] != "true":
      logUniqueIndicators = "false"

if 'logUniqueResources' not in datachannelProps:
   logUniqueResources = "false"
else:
   if datachannelProps['logUniqueResources'] != "false" or datachannelProps['logUniqueResources'] != "true":
      logUniqueResources = "false"

if 'logRawJson' not in datachannelProps:
   if datachannelProps['logRawJson'] != "false" or datachannelProps['logRawJson'] != "true":
      logRawJson = "false"
else:
   if(logRawJson.lower() == "true"):
      jsonLogFileLocation = open(mediatorHome + "/log/rawJson.log", "w")
      jsonLogFileLocation.write("Starting logging")
   
################################
#
# Set up avro schema if required
#
################################

if sourceKafkaDataFormat.lower() == "avro":
   if(os.path.exists(mediatorHome + "/conf/avro-schema.json")):
      schemafile = open(mediatorHome + "/conf/avro-schema.json", "r")
      try:
         schema = json.loads(schemafile.read())
      except:
         print("FATAL: Unable to parse Avro schema file. Please verify that it is the correct format (JSON)")
         logging.info("FATAL: Unable to parse Avro schema file. Please verify that it is the correct format (JSON)")
         exit()
   else:
      print(("FATAL: Source Kafka data format is configured for Avro, but the required Avro schema file does not exist at " + mediatorHome + "/conf/avro-schema.json"))
      print("Please obtain the Avro schema in config and place the JSON in the avro-schema.json file.")
      logging.info("FATAL: Source Kafka data format is configured for Avro, but the required Avro schema file does not exist at " + mediatorHome + "/conf/avro-schema.json")
      logging.info("Please obtain the Avro schema and place the JSON in the avro-schema.json file.")
      exit()

   print(("Going to parse avro schema: " + json.dumps(schema)))
   try:
      parsed_schema = avro.schema.parse(json.dumps(schema))
   except Exception as e:
      logging.info("FATAL: Unable to parse Avro schema. Verify that the schema definition is correct.")
      print("FATAL: Unable to parse avro schema. Verify that the schema definition is correct.")
      print(e)
      exit()
   #reader = avro.io.DatumReader(parsed_schema)
   reader = DatumReader(parsed_schema)
   print("Avro schema parsed successfully")
   print("Properties loaded successfully")



###################
#
# Ignore SSL errors
#
###################

if (not os.environ.get('PYTHONHTTPSVERIFY', '') and getattr(ssl, '_create_unverified_context', None)):
      ssl._create_default_https_context = ssl._create_unverified_context

#ctx = ssl.create_default_context()
#ctx.check_hostname = False
#ctx.verify_mode = ssl.CERT_NONE

   
# Define a publisher queue that will be used to publish metrics to Watson

publishQueue = queue.Queue()
   

####################################################
#
# Connect to Watson Kafka bus if publishing to kafka
#
####################################################

logging.debug("Validate publisher type and if Kafka, configure Kafka properties, and if REST, start a publishQueueThread")


if "kafka" in publisherTypes:

   logging.debug("connecting to watsonKafkaServers: " + watsonKafkaServers)
   
   watsonKafkaConfig = {
        'bootstrap.servers': watsonKafkaServers,
        'client.id': "ibmAIOpsMetrics@" + socket.gethostname(),
        'queue.buffering.max.ms': 5}
   
   if watsonKafkaSSL.lower() == "true":
      kafkasslsettings = {
         'security.protocol' : 'SSL',
         'ssl.ca.location': watsonSSLCaLocation,
         'ssl.certificate.location': watsonSSLCertificateLocation,
         'ssl.key.location': watsonSSLKeyLocation }
      watsonKafkaConfig.update(kafkasslsettings)
   else:
      logging.debug("Watson Kafka connection does not require SSL")
   
   watsonProducer = Producer(watsonKafkaConfig)
   
   watson_admin_client = AdminClient(watsonKafkaConfig)
   topics = watson_admin_client.list_topics().topics
   if not topics:
      logging.info("FATAL: Unable to verify connectivity and topics in the Watson kafka bus at " + watsonKafkaServers + ". Verify kafka configuration, reconfigure, and retry.")
      print(("FATAL: Unable to verify connectivity and topics in the Watson kafka bus at " + watsonKafkaServers + ". Verify kafka configuration, reconfigure, and retry."))
      exit()
   elif watsonKafkaTopicName not in topics:
      print(("FATAL: Watson kafka topic name (" + watsonKafkaTopicName + ") does not exist in the Watson kafka. Available topics: " + topics + ". Ensure proper topic configuration."))
      exit()
   
   logging.debug("Watson AIOps Kafka topic available.")


#############################
#
# Connect to source Kafka bus
#
#############################

kafkasettings = {
    'bootstrap.servers': sourceKafkaServers,
    'group.id': 'waiopsMetric-Restgroup',
    'client.id': 'waiopsMetric-Restclient-1@' + socket.gethostname(),
    'enable.auto.commit': False,
    'session.timeout.ms': 6000,
    'socket.timeout.ms': 3000,
    'max.poll.interval.ms': 6000,
    'default.topic.config': {'auto.offset.reset': 'latest'}
}

if sourceKafkaSSL.lower() == "true":
   kafkasslsettings = {
      'security.protocol' : 'SSL',
      'ssl.ca.location': sourceSSLCaLocation,
      'ssl.certificate.location': sourceSSLCertificateLocation,
      'ssl.key.location': sourceSSLKeyLocation }
   kafkasettings.update(kafkasslsettings)
else:
   logging.debug("Source Kafka connection does not require SSL")


logging.debug("kafka settings are: " + str(kafkasettings))

c = Consumer(kafkasettings)    # is this version buggy? thinks this is a Producer



logging.info("==============================================")
logging.debug("=   Verifying kafka topic - listing topics   =")
logging.info("==============================================")


admin_client = AdminClient(kafkasettings)
topics = admin_client.list_topics().topics
if not topics:
   logging.info("FATAL: Unable to verify connectivity and topics in kafka bus at " + sourceKafkaServers + ". Verify kafka configuration, reconfigure, and retry.")
   print(("FATAL: Unable to verify connectivity and topics in kafka bus at " + sourceKafkaServers + ". Verify kafka configuration, reconfigure, and retry."))
   exit()
elif sourceKafkaTopicName not in topics:
   print(("FATAL: source kafka topic name does not exist in kafka. Available topics: " + str(topics) + ". Ensure proper topic configuration."))
   exit()

logging.debug("Successfully listed topics in the source kafka. Topics returned: " + str(topics))

logging.debug("Subscribing to source kafka topic")
try:
   c.subscribe([sourceKafkaTopicName])
except Exception as e:
   logging.info("FATAL: Unable to connect to Kafka bus at " + sourceKafkaServers + ". Verify Kafka configuration, reconfigure, and retry.")
   print(("FATAL: Unable to connect to Kafka bus at " + sourceKafkaServers + ". Verify Kafka configuration, reconfigure, and retry."))
   exit()
   
logging.debug("Source Kafka Topic available.")


######################
#
# Main processing loop
#
######################

# Ensure that our transformer module is defined and that we can load the module

if 'transformerLibrary' not in datachannelProps:
   print("FATAL: transformerLibrary is not defined in the properties file. Specify which transformer you wish to use.")
   logging.info("FATAL: transformerLibrary is not defined in the properties file. Specify which transformer you wish to use.")
   exit()
else:
   logging.info("Transformer library to use is " + datachannelProps['transformerLibrary'])
   logging.debug("Adding transformers path at " + mediatorHome + "/python/transformers/")
   #sys.path.insert(0, os.path.abspath(mediatorHome + '/python/transformers'))
   #sys.path.insert(0, './transformers/')
   for path in sys.path:
      print(path)
   sys.path.append(os.path.abspath(mediatorHome + '/python/transformers'))
   for path in sys.path:
      print(path)
   import importlib
   try:
      transformerModule = importlib.import_module(datachannelProps['transformerLibrary'])
   except Exception as error:
      logging.info("FATAL: unable to load transformer module " + datachannelProps['transformerLibrary'] + ". Error: " + str(error))
      logging.info(str(error))
      exit()
      



# Set up signal handlers for interrupt signal (e.g. CTRL-C) and HUP signal

signal.signal(signal.SIGINT, shutdownHandler)
signal.signal(signal.SIGHUP, reconfigHandler)




# Start a reader thread to connect to the kafka bus and receive messages

kafkaReaderThread = threading.Thread(target=kafkaReader)
kafkaReaderThread.daemon = True
kafkaReaderThread.start()
#publishThread.join()


# Start a publisher thread that will pick up transformed metric JSON and place it on the Watson kafka topic
# or POST to PI/AIOps or write to a file

if("kafka" in publishTypes):
   publishThread = threading.Thread(target=kafkaQueueReader)
   publishThread.daemon = True
   publishThread.start()
   #publishThread.join()
else:
   # start up a thread to pick up the queue messages and add them to the restMetricGroup["groups"], and publish to rest or file
   logging.debug("publishType is \'rest\' or file, let's start a publishQueueThread")
   publishQueueThread = threading.Thread(target=publishQueueReader)
   publishQueueThread.daemon = True
   publishQueueThread.start()

# Start a performance statistics thread to keep track of various performance metrics (queue depth, etc)

perfStatThread = threading.Thread(target=logTimeDelta, args=(True,))
perfStatThread.daemon = True
perfStatThread.start()
#perfStatThread.join()


# Sleep until shutdown signal received

while threading.active_count() > 0:
    time.sleep(0.1)

