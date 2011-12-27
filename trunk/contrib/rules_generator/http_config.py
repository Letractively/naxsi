#!/usr/bin/python
# try to provide minimal multi-version support
try:
    from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
except ImportError:
    from http.server import BaseHTTPRequestHandler, HTTPServer
try:
    import urlparse
except ImportError:
    import urllib.parse as urlparse
import sqlite3

import pprint
import hashlib
import sys
import os
import argparse
import re
import cgi    

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.do_GET()
    def do_GET(self):
        message = ""
        # if it's a background-forwarded request ...
        if ("naxsi_sig" in self.headers.keys()):
            if params.v > 2:
                print ("Exception catched.")
                print ("ExUrl: "+self.headers["naxsi_sig"])
            nx.eat_rule(self)
            nx.agreggate_rules()
            return
        # user wanna reload its config
        if (self.path.startswith("/write_and_reload")):
            if params.v > 2:
                print ("writting rules, reloading nginx.")
            if self.path.find("?servmd5="):
                nx.dump_rules(self.path[self.path.find("?servmd5=")+9:])
            else:
                nx.dump_rules()
            
            os.system(params.cmd)
            self.send_response(302)
            self.send_header('Location', '/')
            self.end_headers()
            return
        # else, show ui/report
        message = self.ui_report()
        self.send_response(200)
        self.end_headers()
        if sys.version_info > (3, 0):
            self.wfile.write(bytes(message, 'utf-8'))
        else:
            self.wfile.write(message)
        return
    def ui_report(self):
        nbr = nx.get_written_rules_count()
        nbs = nx.get_exception_count()
        message = """<html>
        <style>
        .nx_ok {
        font-size: 100%;
        color: #99CC00;
        }
        .nx_ko {
        font-size: 100%;
        color: #FF0000;
        }
        .lnk_ok a {
        color:green
        }
        .lnk_ko a {
        color:red
        }
        </style>
        <b class="""
        if (nbr > 0):
            message += "nx_ko> "
        else:
            message += "nx_ok> "
        message += "You currently have "+str(nbr)
        message += " rules generated by naxsi </b><br>"
        message += "You have a total of "+str(nbs)+" exceptions hit.</br>"
        if (nbr > 2):
            message += "You should reload nginx's config.</br>"
            message += "<a href='/write_and_reload' style=nx_ko>Write rules and reload for <b>ALL</b> sites.</a></br>"
        message += nx.display_written_rules()
        message += "</html>"
        return (message)

class NaxsiDB:
    def read_text(self):
        try:
            fd = open(params.rules, "r")
        except IOError:
            print ("Unable to open rules file : "+params.rules)
            return
        for rules in fd:
            rid = re.search('id:([0-9]+)', rules)
            if rid is None:
                continue
            ptr = re.search('str:([^"]+)', rules)
            if ptr is None:
                continue
            self.static[str(rid.group(1))] = cgi.escape(ptr.group(1))
        fd.close()
    def dump_rules(self, server=None):
        if server is None:
            fd = open(params.dst, "a+")
        else:
            fd = open(params.dst+"."+hashlib.md5(server).hexdigest(), "a+")
        cur = self.con.cursor()
        if server is None:
            cur.execute("SELECT id, uri, zone, var_name, "
                        "server from tmp_rules where written = 0")
        else:
            cur.execute("SELECT id, uri, zone, var_name, "
                        "server from tmp_rules where written = 0 and server = ?", [server])
        rr = cur.fetchall()
        for i in range(len(rr)):
            tmprule = "BasicRule wl:"+str(rr[i][0])+" \"mz:"
            if len(rr[i][1]) > 0:
                tmprule += "$URL:"+rr[i][1]+"|"
            if len(rr[i][3]) > 0:
                tmprule += "$"+rr[i][2]+"_VAR:"+rr[i][3]+"\" "
            else:
                tmprule += rr[i][2]+"\" "
            tmprule += "; #"+rr[i][4]+"\n"
            cur.execute("UPDATE tmp_rules SET written=1 WHERE id=? and "
                        "uri=? and zone=? and var_name=? and server=?",
                        [rr[i][0], rr[i][1], rr[i][2], rr[i][3], rr[i][4]])
            self.con.commit()
            fd.write(tmprule)
            if params.v > 2:
                print ("Generated Rule : "+tmprule)
        fd.close()
    def gen_write(self, mid, uri, zone, var_name, server):
        cur = self.con.cursor()
        cur.execute("SELECT count(*) from tmp_rules where id=? and uri=? "
                    "and zone=? and var_name=? and server=?", 
                    [mid, uri, zone, var_name, server])
        ra = cur.fetchone()
        if (ra[0] >= 1):
            if params.v > 2:
                print ("already present in tmp_rules ...")
            return
        cur.execute("INSERT INTO tmp_rules (id, uri, zone, var_name, "
                    "server, written) VALUES (?, ?, ?, ?, ?, 0)",
                    [mid, uri, zone, var_name, server])
        self.con.commit()
    def agreggate_rules(self, mid=0, zone="", var_name=""):
        cur = self.con.cursor()
        cur.execute("SELECT id,uri,zone,var_name,server FROM received_sigs"
                    " GROUP BY zone,var_name,id ORDER BY zone,var_name,id")
        rr = cur.fetchall()
        for i in range(len(rr)):
            if len(rr[i][2]) > 0 and len(rr[i][3]) > 0:
                self.gen_write(rr[i][0], "", rr[i][2], rr[i][3], rr[i][4])
                continue
            if len(rr[i][3]) <= 0:
                self.gen_write(rr[i][0], rr[i][1], rr[i][2], rr[i][3], rr[i][4])
                continue
    def cursor(self):
        return self.con.cursor()
    def get_written_rules_count(self, server=None):
        cur = self.con.cursor()
        if server is None:
            cur.execute("SELECT COUNT(id) FROM tmp_rules where written = 0")
        else:
            cur.execute("SELECT COUNT(id) FROM tmp_rules where written = 0 and server = ?", [server])
        ra = cur.fetchone()
        return (ra[0])
    def display_written_rules(self):
        msg = ""
        cur = self.con.cursor()
        cur.execute("SELECT distinct(server) "
                    " FROM tmp_rules")
        rr = cur.fetchall()
        pprint.pprint(rr)
        for i in range(len(rr)):
            print ("adding elems !")
            if self.get_written_rules_count(rr[i][0]) > 0:
                tmpstyle="lnk_ko"
            else:
                tmpstyle="lnk_ok"
            msg += """<a style={4} href='/write_and_reload?servmd5={0}'>
            [write&reload <b>{1}</b></a>|{2} pending rules|
            filename:{3}]</br>""".format(rr[i][0], rr[i][0], 
                                         str(self.get_written_rules_count(rr[i][0])),
                                         params.dst+"."+hashlib.md5(rr[i][0]).hexdigest(),
                                         tmpstyle)
            
        msg += "</br>"
        cur.execute("SELECT id,uri,zone,var_name,server"
                    " FROM tmp_rules where written = 0")
        rr = cur.fetchall()
        if len(rr):
            msg += "Authorizing :</br>"
        for i in range(len(rr)):
            pattern = ""
            if (str(rr[i][0]) in self.static.keys()):
                pattern = nx.static[str(rr[i][0])]
            if len(rr[i][2]) > 0 and len(rr[i][3]) > 0:
                msg += """<b style=nx_ok>[{0}]</b> -- pattern '{1}' 
                ({2}) authorized on URL '{3}' for argument '{4}' 
                of zone {5}</br>""".format(str(rr[i][4]), pattern,
                                           str(rr[i][0]), rr[i][1],
                                           rr[i][3], rr[i][2])
                continue
            if len(rr[i][3]) <= 0:
                msg += """<b style=nx_ok>[{0}]</b> -- 
                pattern '{1}' ({2}) authorized on url '{3}' 
                for zone {4}</br>""".format(str(rr[i][4]),
                                       pattern,
                                       str(rr[i][0]),
                                       rr[i][1],
                                       rr[i][2])
                continue
        return msg
    def get_exception_count(self):
        cur = self.con.cursor()
        cur.execute("SELECT COUNT(id) FROM received_sigs")
        ra = cur.fetchone()
        return (ra[0])
    def eat_rule(self, req):
        currdict = {}
        server = ""
        uri = ""
        ridx = '0'
        tmpdict = urlparse.parse_qsl(req.headers["naxsi_sig"])
        for i in range(len(tmpdict)):
            if (tmpdict[i][0][-1] >= '0' and tmpdict[i][0][-1] <= '9' and
                tmpdict[i][0][-1] != ridx):
                currdict["uri"] = uri
                currdict["server"] = server
                if ("var_name" not in currdict):
                    currdict["var_name"] = ""
                currdict["md5"] = hashlib.md5((currdict["uri"]+
                                               currdict["server"]+
                                               currdict["id"]+
                                               currdict["zone"]+
                                               currdict["var_name"]).encode('utf-8')).hexdigest()
#                print ('#1 here:'+currdict["md5"])
                self.fatdict.append(currdict)
                currdict={}
                ridx = tmpdict[i][0][-1]
            if (tmpdict[i][0].startswith("server")):
                server = tmpdict[i][1]
            if (tmpdict[i][0].startswith("uri")):
                uri = tmpdict[i][1]
            if (tmpdict[i][0].startswith("id")):
                currdict["id"] = tmpdict[i][1]
            if (tmpdict[i][0].startswith("zone")):
                currdict["zone"] = tmpdict[i][1]
            if (tmpdict[i][0].startswith("var_name")):
                currdict["var_name"] = tmpdict[i][1]
        currdict["uri"] = uri
        currdict["server"] = server
        if ("var_name" not in currdict):
            currdict["var_name"] = ""
        currdict["md5"] = hashlib.md5((currdict["uri"]+currdict["server"]+
                                      currdict["id"]+currdict["zone"]+
                                      currdict["var_name"]).encode('utf-8')).hexdigest()
#        print ('#2 here:'+currdict["md5"])
        self.fatdict.append(currdict)
        self.push_to_db(self.fatdict)
    def push_to_db(self, dd):
        cur = self.con.cursor()
#        pprint.pprint(dd)
        for i in range(len(dd)):
            cur.execute("""SELECT count(id) FROM received_sigs WHERE md5=?""", [dd[i]["md5"]])
            ra = cur.fetchone()
            if (ra[0] >= 1):
                continue
            if params.v > 2:
                print ("Pushing to db :")
                pprint.pprint(dd[i])
            cur.execute("INSERT INTO received_sigs (md5, server, id, uri, zone, var_name) VALUES ("+
                        "?, ?, ?, ?, ?, ?)", [dd[i]["md5"], dd[i]["server"], dd[i]["id"], dd[i]["uri"],
                                              dd[i]["zone"], dd[i]["var_name"]])
        self.con.commit()
    def dbcreate(self):
        if params.v > 2:
            print ("Creating (new) database.")
        cur = self.con.cursor()
        cur.execute("CREATE TABLE received_sigs (md5 text, server text, id int, uri text, zone text, var_name text)")
        cur.execute("CREATE TABLE tmp_rules (id int, uri text, zone text, var_name text, written int, server text)")
        self.con.commit()
        print ("Finished DB creation.")
        os.system("touch %s" % params.dst)
        if params.v > 2:
            print ("Touched TMP rules file.")
    def dbinit(self):
        if (self.con is None):
            self.con = sqlite3.connect(params.db)
        cur = self.con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE name='received_sigs'")
        ra = cur.fetchone()
        if (ra is None):
            self.dbcreate()
        if params.v > 2:
            print ("done.")
    def __init__(self):
        self.con = None
        self.fatdict = []
        self.static = {}
        self.dbinit()
        return

class Params(object):
    pass

params = Params()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Naxsi's learning-mode HTTP server.\n"+
                                     "Should be run as root (yes scarry), as it will need to perform /etc/init.d/nginx reload.\n"+
                                     "Should run fine as non-root, but you'll have to manually restart nginx",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--dst', type=str, default='/tmp/naxsi_rules.tmp', help='''Full path to the temp rule file.
                        This file should be included in your naxsi's location configuration file.''')
    parser.add_argument('--db', type=str, default='naxsi_tmp.db', help='''SQLite database file to use.''')
    parser.add_argument('--rules', type=str, default='/etc/nginx/naxsi_core.rules', help='''Path to your core rules file.''')
    parser.add_argument('--cmd', type=str, default='/etc/init.d/nginx reload', help='''Command that will be 
                        called to reload nginx's config file''')
    parser.add_argument('--port', type=int, default=4242, help='''The port the HTTP server will listen to''')
    
    parser.add_argument('-n', action="store_true", default=False, help='''Run the daemon as non-root, don't try to reload nginx.''')
    parser.add_argument('-v', type=int, default=1, help='''Verbosity level 0-3''')
    args = parser.parse_args(namespace=params)
    server = HTTPServer(('localhost', params.port), Handler)
    nx = NaxsiDB()
    nx.read_text()
    print ('Starting server, use <Ctrl-C> to stop')
    server.serve_forever()    
