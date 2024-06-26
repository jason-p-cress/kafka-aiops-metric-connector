
def translateToWatsonMetric(event_dict, ignoreMetrics, counterMetrics, watsonMetricGroup, watsonTopicName):

   import json
   ################################################################################################
   #
   # This is the translation function to translate the Brix json format to the Watson json format
   #
   ################################################################################################

   runError = {}

   # Build WAIOps json
   if("testName" not in event_dict):
      runError["error"] = "WARNING: payload is missing \"testName\" field, which we are expecting to contain the metric name. Will not process metric. JSON: " + json.dumps(event_dict)
      return(runError)
   else:
      try:
         waiopsMetric = dict()
         waiopsMetric["attributes"] = dict()
         waiopsMetric["metrics"] = dict()
         if("hostAddr" in event_dict):
            waiopsMetric["attributes"]["node"] = event_dict["hostAddr"]
         else:
            runError["error"] = "WARNING: payload is missing hostAddr field. Will not process metric. JSON: " + json.dumps(event_dict)
            return(runError)
         if("avgJitter" in event_dict):
            waiopsMetric["metrics"]["avgJitter"] = float(event_dict["avgJitter"])
         if("endToEndDelayAvg" in event_dict):
            waiopsMetric["metrics"]["endToEndDelayAvg"] = float(event_dict["endToEndDelayAvg"])
         else:
            runError["error"] = "WARNING: payload is missing 'avgJitter' field. Will not process metric. JSON: " + json.dumps(event_dict)
            return(runError)
         waiopsMetric["attributes"]["testName"] = event_dict["testName"]
         waiopsMetric["attributes"]["group"] = watsonMetricGroup
         if("avgJitter" in counterMetrics):
            waiopsMetric["attributes"]["accumulators"] = "avgJitter"
         if("endToEndDelayAvg" in counterMetrics):
            waiopsMetric["attributes"]["accumulators"] = "endToEndDelayAvg"
         if("epoch" in event_dict):
            ts = int(event_dict["epoch"]) * 1000
            waiopsMetric["timestamp"] = ts
         else:
            runError["error"] = "WARNING: Brix translation: payload is missing 'epoch' field. Will not process metric. JSON: " + json.dumps(event_dict)
            return(runError)
         waiopsMetric["resourceID"] = waiopsMetric["attributes"]["node"]
         waiopsGroup = {}
         waiopsGroup["groups"] = []
         waiopsGroup["groups"].append(waiopsMetric)
         #logging.debug("posting metric: " + json.dumps(waiopsGroup, indent=4))
         return(waiopsGroup)
      except Exception as error:
         print("Unable to process message: " + json.dumps(event_dict))
         runError["error"] = "An exception occurred in Brix translation: " + str(error)
         return(runError)


