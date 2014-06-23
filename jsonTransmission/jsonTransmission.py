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


class Application(tornado.web.Application):
    def __init__(self):
        configFile = open("config.conf", "r")
        conf = json.loads(configFile.readline())
        configFile.close()
        self.client = motor.MotorClient(conf["hostname"], conf["port"])
        self.db = self.client[conf["database"]]
        self.collection = self.db[conf["collection"]]
        super(Application, self).__init__([
        (r"/", MainHandler),
        (r"/report", ReportHandler),
        ],)

class MainHandler(tornado.web.RequestHandler):
    @tornado.web.asynchronous
    @gen.coroutine
    def post(self):
        self.write(self.request.headers.get("Content-Type"))
        if self.request.headers.get("Content-Type") == "application/json":
            self.json_args = json_decode(self.request.body)
            result = yield self.application.collection.insert(self.json_args)
            self.write("\nRecord for " + self.json_args.get("file") + 
                       " inserted!\n")
        else:
            self.write("\nError!\n")


class ReportHandler(tornado.web.RequestHandler):
    @tornado.web.asynchronous
    @gen.coroutine
    def post(self):
        if self.request.headers.get("Content-Type") == "application/json":
            # Get git hashes and build hashes
            pipeline = [{"$project":{"gitHash":1, "buildHash":1}}, 
                        {"$group":{"_id":{"gitHash":"$gitHash", "build":"$buildHash"}}}]
            cursor =  yield self.application.collection.aggregate(pipeline, cursor={})
            self.write("<html><body>Report:\n")

            while (yield cursor.fetch_next):
                bsonobj = cursor.next_object()
                obj = bsondumps(bsonobj)
                build = bsonobj["_id"]["build"]
                gitHash = bsonobj["_id"]["gitHash"]
                url = self.request.full_url()
                url += "?gitHash=" + gitHash + "&build=" + build
                self.write("<a href=\"" + url + "\"> " + build + ", " 
                           + gitHash + " </a><br />")
            self.write("</body></html>")

        else:
            self.write("\nError!\n")
    
    @tornado.web.asynchronous
    @gen.coroutine
    def get(self):
        args = self.request.arguments
        
        if len(args) == 0:
            # Get git hashes and build hashes
            pipeline = [{"$project":{"gitHash":1, "buildHash":1}}, 
                        {"$group":{"_id":{"gitHash":"$gitHash", "build":"$buildHash"}}}]
            cursor =  yield self.application.collection.aggregate(pipeline, cursor={})
            self.write("<html><body>Report:\n")

            while (yield cursor.fetch_next):
                bsonobj = cursor.next_object()
                obj = bsondumps(bsonobj)
                build = bsonobj["_id"]["build"]
                gitHash = bsonobj["_id"]["gitHash"]
                url = self.request.full_url()
                url += "?gitHash=" + gitHash + "&build=" + build
                self.write("<a href=\"" + url + "\"> " + build + ", " 
                           + gitHash + " </a><br />")
            self.write("</body></html>")

        else:    
            if args.get("gitHash") == None or args.get("build") == None:
                self.write("Error!\n")
                return
            # Generate line count results
            gitHash = args.get("gitHash")[0]
            buildHash = args.get("build")[0]
            self.write(gitHash + ", " + buildHash)
            pipeline = [{"$match":{"file": re.compile("^src\/mongo"), 
                         "gitHash": gitHash, "buildHash": buildHash}}, 
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

            percentage = float(total-noexecTotal)/total * 100
            self.write("\nlines: " + str(total) + ", hit: " + 
                       str(total-noexecTotal) + ", % executed: " + 
                       str(percentage) + "\n")
            # Generate function results
            pipeline = [{"$project": {"file":1,"functions":1}}, {"$unwind":"$functions"},{"$group": { "_id":"$functions.nm", "count" : { "$sum" : "$functions.ec"}}},{"$sort":{"count":-1}}] 
            cursor =  yield self.application.collection.aggregate(pipeline, cursor={})
            noexec = 0
            total = 0
            while (yield cursor.fetch_next):
                bsonobj = cursor.next_object()
                count = bsonobj["count"]
                total += 1
                if count == 0:
                    noexec += 1

            percentage = float(total-noexec)/total * 100
            self.write("\nfunctions: " + str(total) + 
                       ", hit: " + str(total-noexec) + 
                       ", % executed: " + str(percentage) + "\n")
        
if __name__ == "__main__":
    application = Application()
    application.listen(8888)
    tornado.ioloop.IOLoop.instance().start()

