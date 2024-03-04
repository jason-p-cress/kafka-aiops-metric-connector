
def translateToWatsonMetric(event_dict, ignoreMetrics, counterMetrics, watsonMetricGroup, watsonTopicName):

   mkMetrics = {
      "in_bcast_vol_pkt",
      "in_mcast_vol_pkt",
      "in_ucast_vol_pkt",
      "in_errors_vol_pkt",
      "in_discards_vol_pkt",
      "in_vol_bytes",
      "out_bcast_vol_pkt",
      "out_mcast_vol_pkt",
      "out_ucast_vol_pkt",
      "out_errors_vol_pkt",
      "out_discards_vol_pkt",
      "out_vol_bytes",
      "in_vol_pkt",
      "in_bcast_rat",
      "in_mcast_rat",
      "in_ucast_rat",
      "in_error_rat",
      "in_bw_util",
      "in_tput_bps",
      "in_bcast_pps",
      "in_mcast_pps",
      "in_ucast_pps",
      "in_errors_pps",
      "in_discards_pps",
      "in_pps",
      "out_vol_pkt",
      "out_bcast_rat",
      "out_mcast_rat",
      "out_ucast_rat",
      "out_error_rat",
      "out_bw_util",
      "out_tput_bps",
      "out_bcast_pps",
      "out_mcast_pps",
      "out_ucast_pps",
      "out_errors_pps",
      "out_discards_pps",
      "out_pps"
   }

   import json
   #################################################################################################
   #
   # This is the translation function to translate the Meerkat json format to the Watson json format
   #
   #################################################################################################

   runError = {}

   # Build WAIOps json
   if("src" not in event_dict):
      runError["error"] = "WARNING: payload is missing \"src\" field, which we are expecting to contain the metric source. Will not process metric. JSON: " + json.dumps(event_dict) 
      return(runError)
   else:
      if(event_dict["src"] = "snmp-Interface-pr"):
         try:
            waiopsMetric = dict()
            waiopsMetric["attributes"] = dict()
            waiopsMetric["metrics"] = dict()
            if("device_nm" in event_dict):
               waiopsMetric["attributes"]["node"] = event_dict["device_nm"]
            else:
               runError["error"] = "WARNING: payload is missing \"device_nm\" field. Will not process metric. JSON: " + json.dumps(event_dict) 
               return(runError)
            if("if_name" in event_dict):
               component = event_dict["if_nm"]
            else:
               runError["error"] = "WARNING: payload is missing \"if_nm\" field. Will not process metric. JSON: " + json.dumps(event_dict) 
               return(runError)
            waiopsMetric["attributes"]["component"] = component
            waiopsMetric["attributes"]["group"] = watsonMetricGroup
            waiopsMetric["resourceID"] = event_dict["device_nm"] + ":" + component
            # cycle through all of the expected metrics....
            for metric in mkMetrics:
               if(metric in event_dict):
                  if(event_dict[metric] in counterMetrics):
                     waiopsMetric["attributes"]["accumulators"] = event_dict[metric]
            if("clock" in event_dict):
               ts = str(int(event_dict["clock"] * 1000))
               waiopsMetric["timestamp"] = ts
            else:
               runError = "WARNING: payload is missing 'clock' field. Will not process metric. JSON: " + json.dumps(event_dict) 
               return(runError)
            waiopsMetric["tenantID"] = watsonTopicName
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

