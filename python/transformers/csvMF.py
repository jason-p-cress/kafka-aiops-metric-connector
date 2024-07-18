#!/usr/bin/python3.11

def translateToWatsonMetric(event_dict, ignoreMetrics, counterMetrics, watsonMetricGroup, watsonTopicName):

   import time
   from calendar import timegm

   runError = {}
   
   csvHeader = [ "START_TIMESTAMP" , "STOP_TIMESTAMP" , "TRAN_ID" , "OMEG_UMBR_TRAN" , "CORR_UOWID" , "TRANSACTION_NUM" , "MVS_SYSTEM_ID" , "CICS_GEN_APPLID" , "ELAPSED_TIME" , "CPU_TIME" , "RMI_TIME" , "SUSP_TIME" , "DISP_CICS_USER" , "QR_DIST_TIME" , "L8_TCB_DISP_TIME" , "QR_CPU_TIME" , "KY8CPUT_TOD" , "RMI_SUSP_TIME" , "DB2_REQS_COUNT" ]


   metricsOfInterest = { "ELAPSED_TIME" , "CPU_TIME" , "RMI_TIME" , "SUSP_TIME" , "DISP_CICS_USER" , "QR_DIST_TIME" , "L8_TCB_DISP_TIME" , "QR_CPU_TIME" , "KY8CPUT_TOD" , "RMI_SUSP_TIME" , "DB2_REQS_COUNT" }

   # Quick sanity check to validate that the number of columns are what we expect as defined in the csvHeader

   if len(event_dict.split(",")) != len(csvHeader):
      runError["error"] = "ERROR: CSV entry received from Kafka does not match what we expect - number of fields are mismatched... expected: " + str(len(csvHeader)) + ", received: " + str(len(event_dict.split(",")))
      return(runError)

   counter = 0
   fullMetricDict = {}

   for item in csvHeader:
   
      fullMetricDict[item] = event_dict.split(",")[counter]
      counter+=1


   try:
      waiopsMetric = dict()
      waiopsMetric["attributes"] = dict()
      waiopsMetric["metrics"] = dict()
      waiopsMetric["attributes"]["node"] = fullMetricDict["MVS_SYSTEM_ID"] + ":" + fullMetricDict["CICS_GEN_APPLID"]
      waiopsMetric["attributes"]["application"] = fullMetricDict["TRAN_ID"]
      waiopsMetric["attributes"]["group"] = watsonMetricGroup
      for metric in metricsOfInterest:
         thisMetric = {}
         thisMetric[metric] = fullMetricDict[metric]
         waiopsMetric["metrics"][metric] = float(fullMetricDict[metric])
         if metric in counterMetrics:
            waiopsMetric["attributes"]["accumulators"] = event_dict["name"]
      waiopsMetric["resourceID"] = waiopsMetric["attributes"]["node"] + ":" + waiopsMetric["attributes"]["application"]
      utc_time = time.strptime(fullMetricDict["START_TIMESTAMP"], "%Y-%m-%dT%H:%M:%S.%fZ")
      waiopsMetric["timestamp"] = timegm(utc_time) * 1000
      waiopsGroup = {}
      waiopsGroup["groups"] = []
      waiopsGroup["groups"].append(waiopsMetric)
      print("Returning transformed metric...")
      return(waiopsGroup)
   except Exception as error:
      print("An exception occurred: " + str(error))
      print("Unable to process message: " + str(event_dict))
      runError = "An exception occurred: " + str(error)
      return(runError)

#event_dict = "2023-11-01T11:05:04.262Z,2023-11-01T11:05:04.278Z,AGMU,,225870699D28,52,PT2A,CTBR01  ,0.016415,0.0020785859375,0.0,1.133642578125E-5,0.0,0.013752107421875,0.0,0.00179522216796875,0.0,0.0,0"

#metricJson = translateToWatsonMetric(event_dict, "", "", "", "")
#print(metricJson)


