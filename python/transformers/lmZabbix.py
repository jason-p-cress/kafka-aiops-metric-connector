
def translateToWatsonMetric(event_dict, ignoreMetrics, counterMetrics, watsonMetricGroup, watsonTopicName):

   import json
   ################################################################################################
   #
   # This is the translation function to translate the SevOne json format to the Watson json format
   #
   ################################################################################################

   runError = {}

   # Build WAIOps json
   if("name" not in event_dict):
      runError["error"] = "WARNING: payload is missing \"name\" field, which we are expecting to contain the metric name. Will not process metric. JSON: " + json.dumps(event_dict) 
      return(runError)
   else:
      try:
         waiopsMetric = dict()
         waiopsMetric["attributes"] = dict()
         waiopsMetric["metrics"] = dict()
         if("host" in event_dict["host"]):
            waiopsMetric["attributes"]["node"] = event_dict["host"]["host"]
         else:
            runError["error"] = "WARNING: payload is missing host field. Will not process metric. JSON: " + json.dumps(event_dict) 
            return(runError)
         if("item_tags" in event_dict):
            foundComponentTag = 0
            foundMetricTag = 0
            component = ""
            metricname = ""
            for tag in event_dict["item_tags"]:
               #print("evaluating tag: " + tag["tag"])
               if tag["tag"] == "KafkaSubcomponent":
                  component = tag["value"]
                  foundComponentTag = 1
               if tag["tag"] == "KafkaMetric":
                  metricname = tag["value"]
                  foundMetricTag = 1
            if(foundComponentTag !=1 or foundMetricTag != 1):
               runError["error"] = "Missing either the metric tag or component found for the following metric JSON entry. Will not process metric: " + json.dumps(event_dict)
               return(runError)
         else:
            runError["error"] = "No 'item_tags' found in the payload. Will not process this metric. JSON: " + json.dumps(event_dict)
            return(runError)
         if("value" in event_dict):
            waiopsMetric["metrics"][metricname] = float(event_dict["value"])
         else:
            runError["error"] = "WARNING: payload is missing 'name' field. Will not process metric. JSON: " + json.dumps(event_dict) 
            return(runError)
         waiopsMetric["attributes"]["component"] = component
         waiopsMetric["attributes"]["group"] = watsonMetricGroup
         if(event_dict["name"] in counterMetrics):
            waiopsMetric["attributes"]["accumulators"] = event_dict["name"]
         if("clock" in event_dict):
            ts = str(int(event_dict["clock"] * 1000))
            waiopsMetric["timestamp"] = ts
         else:
            runError = "WARNING: payload is missing 'clock' field. Will not process metric. JSON: " + json.dumps(event_dict) 
            return(runError)
         waiopsMetric["tenantID"] = watsonTopicName
         waiopsMetric["resourceID"] = event_dict["host"]["host"] + ":" + component
         waiopsGroup = {}
         waiopsGroup["groups"] = []
         waiopsGroup["groups"].append(waiopsMetric)
         #logging.debug("posting metric: " + json.dumps(waiopsGroup, indent=4))
         return(waiopsGroup)
      except Exception as error:
         print("An exception occurred: " + str(error))
         print("Unable to process message: " + json.dumps(event_dict))
         runError = "An exception occurred: " + str(error)
         return(runError)

