import json
import logging
import sqlite3

from flask import Flask, escape, request, jsonify, send_file

logging.basicConfig(level=logging.INFO,
                    filename='err.log',
                    filemode='a',
                    format='%(asctime)s - %(pathname)s[line:%(lineno)d] - %(levelname)s: %(message)s')

app = Flask(__name__)


@app.route('/')
def hello():
    name = request.args.get("name", "World")
    return f'Hello, {escape(name)}!'


"""
process new test
"""


# convert returned tuple from sqlite into json format
def tuple2json(tp, column_name):
    res = {}
    for i, v in enumerate(column_name):
        res[v] = tp[i]
    return res


# # get test id by subject name
# def getId(subject_name,db):
#     for test in db:
#         # found test
#         if test['subject'] == subject_name:
#             return test["test_id"]
#     # test not found
#     return -1

# create a new test by request
def create_test(info):
    keys = json.dumps(info['answer_keys'])
    conn = sqlite3.connect('tests.db')
    cur = conn.cursor()
    q1 = "SELECT * FROM test WHERE subject=?;"
    cur.execute(q1, (info['subject'],))
    val = cur.fetchall()
    if not val:
        query = "INSERT INTO test VALUES (null,?,?);"
        cur.execute(query, (info['subject'], keys))
    else:
        query = "UPDATE test SET answer_keys=? WHERE subject=?;"
        cur.execute(query, (keys, info['subject']))
    cur.execute(q1, (info['subject'],))
    val = cur.fetchone()
    cur.close()
    conn.commit()
    conn.close()
    val = tuple2json(val, ['test_id', 'subject', 'answer_keys'])
    # deserialize the answer key
    val['answer_keys'] = json.loads(val['answer_keys'])
    val['submissions'] = []
    return val


# post a new test
@app.route('/tests', methods=['POST'])
def post_test():
    if not request.json:
        return "Wrong Value"
    info = request.json
    return jsonify(create_test(info)), 201


"""
process new submission
"""


# convert json file into dic if need
# read a json file
def pdf2json(pdf):
    submission = {
        "subject": pdf["subject"],
        "name": pdf["name"],
        "answer": pdf["answer"]
    }
    return submission


# validate a char
def valid(s):
    if not str.isalpha(s):
        return False
    return 'A' <= s <= 'D'


# get submission by test


# validate and grade a submission, if valid add the submission into table
def grade(submission, tid):
    # grade and create result
    # res with actual and expected key
    res = {}
    conn = sqlite3.connect('tests.db')
    cur = conn.cursor()
    # select the test
    get_test = "SELECT * FROM test WHERE test_id=?;"
    cur.execute(get_test, (tid,))
    test = cur.fetchone()
    test = tuple2json(test, ['test_id', 'subject', 'answer_keys'])
    # first validate the subject name
    if test['subject'] != submission['subject']:
        return "Submit for test %s! but get %s" % (test['subject'], submission['subject'])
    test['answer_keys'] = json.loads(test['answer_keys'])
    # calculate the score
    score = 0
    for k, v in test['answer_keys'].items():
        s_v = submission['answers'][k]
        if not valid(s_v):
            return "Wrong Format at number %s" % k
        if v == s_v:
            score += 1
        res[k] = {
            "actual": s_v,
            "expected": v
        }
    # insert submission into table
    add_sub = "INSERT INTO submission VALUES (null, ?,?,?,?,?);"
    loc = ""
    cur.execute(add_sub, (loc, submission['subject'], submission['name'], score, json.dumps(res)))
    sid = cur.lastrowid
    logging.info("current row is %s" % sid)
    with open('files/%s.json' % sid, 'w') as f:
        json.dump(submission, f)
    # update the file location
    upd = "UPDATE submission SET scantron_url=? WHERE scantron_id=?;"
    loc = "http://localhost:5000/files/%s.json" % sid
    cur.execute(upd, (loc, sid))
    # return the submission
    get_sub = "SELECT * FROM submission WHERE scantron_id=?"
    cur.execute(get_sub, (sid,))
    sc = cur.fetchone()
    cur.close()
    conn.commit()
    conn.close()
    sc = tuple2json(sc, ['scantron_id', 'scantron_url', 'subject', 'name', 'score', 'result'])
    sc['result'] = json.loads(sc['result'])
    return sc


@app.route('/files/<string:fname>')
def get_file(fname):
    return send_file('files/%s' % fname, as_attachment=True, attachment_filename=fname)


# post a pdf submission and return the result
@app.route('/tests/<int:tid>/scantrons', methods=['POST'])
def post_sub(tid):
    # get file data
    # return "nothing",200
    sub = request.files['data']
    sub.seek(0)
    sf = sub.read()
    dc = sf.decode()
    js = json.loads(dc)
    # logging.info("The received type is %s" % type(sub))
    # logging.info("The read type is %s" % type(sf))
    # logging.info("The decoded type is %s" % type(dc))
    # logging.info("The loaded type is %s" % type(js))

    return grade(js, tid), 201


# get all scantron submissions of a test
@app.route('/tests/<int:tid>')
def get(tid):
    conn = sqlite3.connect('tests.db')
    cur = conn.cursor()
    # get the test
    get_test = "SELECT * FROM test WHERE test_id=?"
    cur.execute(get_test, (tid,))
    test = cur.fetchone()
    if not test:
        return "Test not found!", 404
    res = tuple2json(test, ['test_id', 'subject', 'answer_keys'])
    res['answer_keys'] = json.loads(res['answer_keys'])
    # get the related submissions
    get_subs = "SELECT * FROM submission WHERE subject=?"
    cur.execute(get_subs, (res['subject'],))
    scan = cur.fetchall()
    cur.close()
    conn.commit()
    conn.close()
    subs = []
    for sc in scan:
        sc = tuple2json(sc, ['scantron_id', 'scantron_url', 'subject', 'name', 'score', 'result'])
        sc['result'] = json.loads(sc['result'])
        subs.append(sc)
    res['submissions'] = subs
    return res
