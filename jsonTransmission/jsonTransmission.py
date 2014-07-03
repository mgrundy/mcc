import sys
import optparse
import pymongo
from pymongo import MongoClient
import json
from bson.json_util import dumps as bsondumps
import re
from pprint import pprint

import tornado.ioloop
import tornado.web
from tornado.escape import json_decode
import motor
from tornado import gen
import ssl
import tornado.httpclient

import pipelines


class Application(tornado.web.Application):
    def __init__(self):
        configFile = open("config.conf", "r")
        conf = json.loads(configFile.readline())
        configFile.close()
        self.client = motor.MotorClient(host=conf["hostname"], port=conf["port"], 
                                        ssl=True, ssl_certfile=conf["clientPEM"], 
                                        ssl_cert_reqs=ssl.CERT_REQUIRED, 
                                        ssl_ca_certs=conf["CAfile"])

        self.client.the_database.authenticate(conf["username"], mechanism="MONGODB-X509")

        self.db = self.client[conf["database"]]
        self.collection = self.db[conf["collection"]]
        self.metaCollection = self.db[conf["metaCollection"]]
        self.covCollection = self.db[conf["covCollection"]]
        self.httpport = conf["httpport"]
       
        super(Application, self).__init__([
        (r"/", MainHandler),
        (r"/report", ReportHandler),
        (r"/data", DataHandler),
        (r"/meta", MetaHandler),
        ],)


class MainHandler(tornado.web.RequestHandler):
    @tornado.web.asynchronous
    @gen.coroutine
    def post(self):
        self.write(self.request.headers.get("Content-Type"))
        if self.request.headers.get("Content-Type") == "application/json":
            self.json_args = json_decode(self.request.body)
      
            # Insert information
            result = yield self.application.collection.insert(self.json_args)
            self.write("\nRecord for " + self.json_args.get("file") + 
                       " inserted!\n")
        else:
            self.write("\nError!\n")


class DataHandler(tornado.web.RequestHandler):
    @tornado.web.asynchronous
    @gen.coroutine
    def post(self):
        self.json_args = json_decode(self.request.body)
        query = {}
        cursor = None # Cursor with which to traverse query results
        if "_id" in self.json_args:
            cursor = self.application.covCollection.find(query)
            query["_id"] = self.json_args["_id"]
            while (yield cursor.fetch_next):
                bsonobj = cursor.next_object()
                self.write(bsonobj)
        else:
            gitHash = self.json_args["gitHash"]
            buildID = self.json_args["buildID"]
            fileName = self.json_args["file"]

            if "testName" in self.json_args:
                testName = self.json_args["testName"]
                pipeline = [{"$match":{"file": fileName, "gitHash": gitHash, "buildID": buildID, "testName": testName}}, {"$project":{"file":1, "lc":1}}, {"$unwind": "$lc"}, {"$group":{"_id": {"file": "$file", "line": "$lc.ln"}, "count":{"$sum": "$lc.ec"}}}]
   
            else:
                pipeline = [{"$match":{"file": fileName, "gitHash": gitHash, "buildID": buildID}}, {"$project":{"file":1, "lc":1}}, {"$unwind": "$lc"}, {"$group":{"_id": {"file": "$file", "line": "$lc.ln"}, "count":{"$sum": "$lc.ec"}}}]
       
            cursor =  yield self.application.collection.aggregate(pipeline, cursor={})
            result = {}
            result["counts"] = []
            executedLines = []
            nonExecutedLines = []
            while (yield cursor.fetch_next):
                bsonobj = cursor.next_object()
                if not "file" in result:
                    result["file"] = bsonobj["_id"]["file"]
                result["counts"].append({"l": bsonobj["_id"]["line"], "c": bsonobj["count"]})
            
            self.write(result)


class MetaHandler(tornado.web.RequestHandler):
    @tornado.web.asynchronous
    @gen.coroutine
    def post(self):
        self.json_args = json_decode(self.request.body)
        
        # Generate line count results
        gitHash = self.json_args["_id"]["gitHash"]
        buildID = self.json_args["_id"]["buildID"]
        self.write(gitHash + ", " + buildID)
        pipeline = [{"$match":{"file": re.compile("^src\/mongo"), 
                     "gitHash": gitHash, "buildID": buildID}}, 
                    {"$project":{"file":1, "lc":1}}, {"$unwind":"$lc"}, 
                    {"$group":{"_id":"$file", "count":{"$sum":1}, 
                     "noexec":{"$sum":{"$cond":[{"$eq":["$lc.ec",0]},1,0]}}}  }]

        cursor =  yield self.application.collection.aggregate(pipeline, cursor={})
        total = 0
        noexecTotal = 0
        while (yield cursor.fetch_next):
            bsonobj = cursor.next_object()
            obj = bsondumps(bsonobj)
            count = bsonobj["count"]
            noexec = bsonobj["noexec"]
            total += count
            noexecTotal += noexec

        self.json_args["lineCount"] = total
        self.json_args["lineCovCount"] = total-noexecTotal
        self.json_args["lineCovPercentage"] = float(total-noexecTotal)/total * 100


        # Generate function results
        pipeline = [{"$project": {"file":1,"functions":1}}, {"$unwind":"$functions"},
                    {"$group": { "_id":"$functions.nm", 
                                 "count" : { "$sum" : "$functions.ec"}}},
                    {"$sort":{"count":-1}}] 
        cursor =  yield self.application.collection.aggregate(pipeline, cursor={})
        noexec = 0
        total = 0
        while (yield cursor.fetch_next):
            bsonobj = cursor.next_object()
            count = bsonobj["count"]
            total += 1
            if count == 0:
                noexec += 1

        self.json_args["funcCount"] = total
        self.json_args["funcCovCount"] = total-noexec
        self.json_args["funcCovPercentage"] = float(total-noexec)/total * 100
  
        # Insert meta-information
        try:
            result = yield self.application.metaCollection.insert(self.json_args)
        except tornado.httpclient.HTTPError as e:
            print "Error:", e

        # Generate coverage data by directory
        pipelines.line_pipeline[0]["$match"]["gitHash"] = self.json_args["_id"]["gitHash"]
        pipelines.function_pipeline[0]["$match"]["gitHash"] = self.json_args["_id"]["gitHash"]
        pipelines.line_pipeline[0]["$match"]["buildID"] = self.json_args["_id"]["buildID"]
        pipelines.function_pipeline[0]["$match"]["buildID"] = self.json_args["_id"]["buildID"]

        cursor =  yield self.application.collection.aggregate(pipelines.line_pipeline, cursor={})
        while (yield cursor.fetch_next):
            bsonobj = cursor.next_object()
            
            # Generate line coverage percentage
            lineCount = bsonobj["lineCount"]
            lineCovCount = bsonobj["lineCovCount"]
            bsonobj["lineCovPercentage"] = float(lineCovCount)/lineCount * 100
            result = yield self.application.covCollection.insert(bsonobj)
        
        cursor =  yield self.application.collection.aggregate(pipelines.function_pipeline, cursor={})
        while (yield cursor.fetch_next):
            bsonobj = cursor.next_object()

            # Generate function coverage percentage
            funcCount = bsonobj["funcCount"]
            funcCovCount = bsonobj["funcCovCount"]
            funcCovPercentage = float(funcCovCount)/funcCount * 100
            result = yield self.application.covCollection.update({"_id": bsonobj["_id"]}, {"$set": {"funcCount": bsonobj["funcCount"], "funcCovCount": bsonobj["funcCovCount"], "funcCovPercentage": funcCovPercentage}})


class ReportHandler(tornado.web.RequestHandler):
    @tornado.web.asynchronous
    @gen.coroutine
    def get(self):
        args = self.request.arguments
        url = self.request.full_url()

        if len(args) == 0:
            # Get git hashes and build IDs 
            cursor =  self.application.metaCollection.find()
            results = []

            while (yield cursor.fetch_next):
                bsonobj = cursor.next_object()
                results.append(bsonobj)

            self.render("templates/report.html", results=results, url=url)
        else:    
            if args.get("gitHash") == None or args.get("buildID") == None:
                self.write("Error!\n")
                return

            gitHash = args.get("gitHash")[0]
            buildID = args.get("buildID")[0]
            query = {"_id": {"gitHash": gitHash, "buildID": buildID}}
            cursor = self.application.metaCollection.find(query)
            metaResult = None
            dirResults = []
            
            # Get summary results
            while (yield cursor.fetch_next):
                bsonobj = cursor.next_object()
                metaResult = bsonobj
           
            query = {"_id.gitHash": gitHash, "_id.buildID": buildID}
            cursor = self.application.covCollection.find(query)
            
            # Get directory results
            while (yield cursor.fetch_next):
                bsonobj = cursor.next_object()
                dirResults.append(bsonobj)
            self.render("templates/directory.html", result=metaResult, directories=dirResults, url=url)



if __name__ == "__main__":
    application = Application()
    application.listen(application.httpport)
    tornado.ioloop.IOLoop.instance().start()

