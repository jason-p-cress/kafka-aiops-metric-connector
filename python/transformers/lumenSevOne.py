def translateToWatsonMetric(event_dict, ignoreMetrics, counterMetrics, watsonMetricGroup, watsonTopicName):

   ################################################################################################
   #
   # This is the translation function to translate the SevOne json format to the Watson json format
   #
   ################################################################################################

   import json

   # Build WAIOps json
   try:
      waiopsMetric = dict()
      waiopsMetric["attributes"] = dict()
      waiopsMetric["metrics"] = dict()
      if("pmIndicator" in event_dict):
         waiopsMetric["metrics"][event_dict["pmIndicator"]] = float(event_dict["pmValue"])
      else:
         runError["error"] = "ERROR: metric is missing the \"pmIndicator\" field. Will not process metric: " + json.dumps(event_dict) 
         return(runError)
      if("customer" in event_dict):
         waiopsMetric["attributes"]["node"] = event_dict["customer"]
      else:
         runError["error"] = "ERROR: metric is missing the \"customer\" field. Will not process metric: " + json.dumps(event_dict) 
         return(runError)
      #waiopsMetric["attributes"]["interface"] = event_dict["objectName"]
      waiopsMetric["attributes"]["group"] = watsonMetricGroup
      waiopsMetric["attributes"]["subcomponent"] = event_dict["pmObject"]
      if(event_dict["pmIndicator"] in counterMetrics):
         waiopsMetric["attributes"]["accumulators"] = event_dict["pmIndicator"]
      if("pmReportingTime" in event_dict):
         waiopsMetric["timestamp"] = str(event_dict["pmReportingTime"])
      else:
         runError["error"] = "ERROR: metric is missing the \"pmReportingTime\" field. Will not process metric: " + json.dumps(event_dict)
         return(runError)
      waiopsMetric["tenantID"] = watsonTopicName
      if("pmObject" in event_dict):
         waiopsMetric["resourceID"] = event_dict["customer"] + ":" + event_dict["pmObject"]
      else:
         waiopsMetric["resourceID"] = event_dict["customer"]
      waiopsGroup = {}
      waiopsGroup["groups"] = []
      waiopsGroup["groups"].append(waiopsMetric)
      return(waiopsGroup)
   except Exception as error:
      print("An exception occurred: " + str(error))
      print("Unable to process message: " + json.dumps(event_dict))
      runError = "An exception occurred: " + str(error)
      return(runError)
