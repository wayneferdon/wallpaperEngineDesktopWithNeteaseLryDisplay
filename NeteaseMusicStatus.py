
import datetime
import json
import os
import re
import sys
import time
from os.path import expanduser
import requests
import urllib
from threading import Thread
import struct
import time
import hashlib
import base64
import socket
import time
import types
import multiprocessing
import os
from pykakasi import kakasi, wakati


# import win32api
# import win32gui
# ct = win32api.GetConsoleTitle()
# hd = win32gui.FindWindow(0, ct)
# win32gui.ShowWindow(hd, 0)


# from Tail import Tail

reg_url = "[-a-zA-Z0-9@:%._\+~#=]{2,256}\.[a-z]{2,6}\b([-a-zA-Z0-9@:%_\+.~#?&//=]*)"
localAppdata = os.getenv("LOCALAPPDATA")
log_path = expanduser(localAppdata + r"\Netease\CloudMusic\cloudmusic.log")


def strLrc(text):
    if text is None:
        return ''
    else:
        return text


def is_cjk(char):
    ranges = [
        {"from": ord(u"\u3300"), "to": ord(u"\u33ff")},  # compatibility ideographs
        {"from": ord(u"\ufe30"), "to": ord(u"\ufe4f")},  # compatibility ideographs
        {"from": ord(u"\uf900"), "to": ord(u"\ufaff")},  # compatibility ideographs
        {"from": ord(u"\U0002F800"), "to": ord(u"\U0002fa1f")},  # compatibility ideographs
        {"from": ord(u"\u30a0"), "to": ord(u"\u30ff")},  # Japanese Kana
        {"from": ord(u"\u2e80"), "to": ord(u"\u2eff")},  # cjk radicals supplement
        {"from": ord(u"\u4e00"), "to": ord(u"\u9fff")},
        {"from": ord(u"\u3400"), "to": ord(u"\u4dbf")},
        {"from": ord(u"\U00020000"), "to": ord(u"\U0002a6df")},
        {"from": ord(u"\U0002a700"), "to": ord(u"\U0002b73f")},
        {"from": ord(u"\U0002b740"), "to": ord(u"\U0002b81f")},
        {"from": ord(u"\U0002b820"), "to": ord(u"\U0002ceaf")}  # included as of Unicode 8.0
    ]
    return any([range["from"] <= ord(char) <= range["to"] for range in ranges])


def cjk_substrings(string):
    i = 0
    while i < len(string):
        if is_cjk(string[i]):
            start = i
            while is_cjk(string[i]):
                i += 1
                if i >= len(string):
                    break
            yield string[start:i]
        i += 1


def kanjiSplite(string):
    for sub in cjk_substrings(string):
        string = string.replace(sub, "//splite//" + sub + "//splite//")
    stringList = string.split("//splite//")
    if "" in stringList:
        removeAll(stringList, "")
    return stringList


class TailError(Exception):
    def __init__(self, msg):
        self.message = msg

    def __str__(self):
        return self.message


class NeteaseMusicStatus():
    @staticmethod
    def _is_json(text):
        return text.strip().startswith("{")

    def __init__(self):
        self.monitor_path = log_path
        self.outPut_path = r'.\outPut.html'
        self.playState = 0
        """ platState:
            0   not playing
            1   playing
            2   software not on
        """
        self.currentSong = False
        self.currentSongLrc = False
        self.currentSongLength = 0
        self.last_update = 0

        self.lastResumeTime = 0
        self.lastPauseTime = 0
        self.lastPosition = 0

        self.check_file_validity()
        self.try_count = 0
        self.currentLrc = {'lrc': '', 'tlrc': ''}
        self.currentTLrc = {'lrc': '', 'tlrc': ''}
        self.nextLrc = {'lrc': '', 'tlrc': ''}
        self.nextTLrc = {'lrc': '', 'tlrc': ''}
        self.currentLrcTime = 0
        self.nextLrcTime = 0
        self.songLrcKeyTime = []
        self.outPutLrc = ''
        self.initializing = True
        # print("----------------------")
        # print('start initializing')
        self.kakasi = kakasi()
        self.wakati = wakati()
        self.wakatiConv = self.wakati.getConverter()

        try:
            self.file_ = open(self.monitor_path, 'r', encoding='utf-8')
            self.size = os.path.getsize(self.monitor_path)
            # Go to the end of file
            self.file_.seek(0, 2)
        except:
            raise

        lineList = self.getLastLines(1000000)
        if lineList is not None:
            lll = len(lineList)
            lineIndex = -1
            while True:
                try:
                    lineIndex += 1
                    lineItem = lineList[lineIndex]
                    if lineIndex > lll:
                        break
                    lineItem = lineItem.decode('utf-8')

                    try:
                        # print(lineItem)
                        self.callback_log(lineItem, self.initializing)
                    except:
                        pass
                except IndexError:
                    break
        with open(self.outPut_path, 'w', encoding='utf-8') as outPutFile:
            outPutFile.write('')

        # print('time: ', self.last_update)
        # print('song id:', self.currentSong)
        # print('state: ', self.playState)
        # print('length: ', self.currentSongLength)
        # print('current position: ', self.lastPosition)
        # print('lastResumeTime: ', self.lastResumeTime)
        # print('lastPauseTime: ', self.lastPauseTime)

        if self.currentSong:
            if self.playState == 1:
                currentTime = time.time()
                currentTimePosition = currentTime - self.lastResumeTime + self.lastPosition
            else:
                currentTimePosition = self.lastPosition
            self.getLrc()
            # print('end initializing')
            # print("----------------------")
            self.setCurrentLrc(currentTimePosition)
            # print(self.currentLrc)
            # print(self.currentTLrc)
            # print(self.nextLrc)
            # print(self.nextTLrc)
            self.outPutCurrentLrc()
        # else:
            # print('end initializing')
            # print("----------------------")
        self.initializing = False

    def kakasiConver(self, source, mode):
        self.kakasi.setMode("H", mode)  # Hiragana to ascii, default: no conversion
        self.kakasi.setMode("K", mode)  # Katakana to ascii, default: no conversion
        self.kakasi.setMode("J", mode)  # Japanese to ascii, default: no conversion
        self.kakasi.setMode("s", True)  # add space, default: no separator
        self.kakasi.setMode("C", True)  # capitalize, default: no capitalize
        self.kaksiConv = self.kakasi.getConverter()
        return self.kaksiConv.do(source)



    def getLastLines(self, length):
        filePath = self.monitor_path
        try:
            fileSize = os.path.getsize(filePath)
            if fileSize == 0:
                return None
            else:
                with open(filePath, 'rb') as fp:  # to use seek from end, must use mode 'rb'
                    offset = -length  # initialize offset
                    while -offset < fileSize:  # offset cannot exceed file size
                        fp.seek(offset, 2)  # read#offset chars from eof(represent by number'2')
                        lines = fp.readlines()  # read from fp to eof
                        if len(lines) >= 2:  # if contains at least 2 lines
                            return lines  # then last line is totally included
                        else:
                            offset *= 2  # enlarge offset
                    fp.seek(0)
                    lines = fp.readlines()
                    return lines
        except FileNotFoundError:
            # print(filePath + ' not found!')
            return None, False


    def reload_monitor_path(self):
        """ Reload tailed file when it be empty be `echo "" > tailed file`, or
            segmentated by logrotate.
        """
		# try:
		# 	self.file_.
        try:
            self.file_ = open(self.monitor_path, "rb")
            self.size = os.path.getsize(self.monitor_path)
            # Go to the head of file
            self.file_.seek(0, 1)
            return True
        except:
            return False

    def callback_log(self, content, initializing=False):
        validInfo = False

        if 'App exit' in content:
            if self.playState == 1:
                self.lastPosition = time.time() - self.lastResumeTime + self.lastPosition
            self.playState = 2
            logTime = time.time()
            validInfo = 'exit'
            # if not initializing:
                # print('app exit')

        elif "[info]" in content:
            content = content.strip().strip('\n')
            result = re.split('\[info]', content)
            logInfo = result[1]
            logTime = re.split('\[(.*?)\]', result[0])
            logTime = time.mktime(datetime.datetime.fromisoformat(logTime[3]).timetuple())


            if 'player._$play' in logInfo:
                playSong = re.split('"', logInfo)
                playSong = re.split('_', playSong[1])
                self.currentSong = playSong[0]
                if not initializing:
                    # print('play')
                    self.getLrc()
                if self.playState != 2:
                    self.lastPosition = 0
                self.playState = 0  # need to wait for load and resume
                validInfo = 'play'

            elif '__onAudioPlayerLoad' in logInfo:

                songLength = re.split('\t', logInfo)
                songLength = json.loads(songLength[0])
                self.currentSongLength = songLength['duration']
                validInfo = 'load'
                # if not initializing:
                    # print('load')
            elif '_$setPosition' in logInfo:
                position = re.split('\t', logInfo)
                position = json.loads(position[0])
                # position = eval(position)
                self.lastPosition = position['ratio'] * self.currentSongLength
                validInfo = 'setPosition'
                if self.playState == 1:
                    if initializing:
                        self.lastResumeTime = logTime
                    else:
                        self.lastResumeTime = time.time()
                # if not initializing:
                    # print('setPosition')
            elif 'player._$resume do' in logInfo:
                self.playState = 1
                self.lastResumeTime = logTime
                validInfo = 'resume'
                # if not initializing:
                    # print('resume')
            elif 'player._$pause do' in logInfo:
                validInfo = 'pause'
                if self.playState == 1:
                    self.playState = 0
                    self.lastPosition = logTime - self.lastResumeTime + self.lastPosition
                    self.lastPauseTime = logTime
                # if not initializing:
                    # print('pause')

        if validInfo:
            if initializing and self.currentSong and self.playState and self.currentSongLength and self.lastPosition:
                return True
            # elif not initializing:
            self.last_update = logTime
            if not initializing:
                # print('time: ', self.last_update)
                # if validInfo == 'load':
                    # print('song id:', self.currentSong)
                    # print('length: ', self.currentSongLength)
                # if validInfo in ['play', 'resume', 'pause', 'exit']:
                    # print('state: ', self.playState)
                # if validInfo in ['play', 'resume', 'pause', 'exit', 'setPosition']:
                    # print('current position: ', self.lastPosition)
                # if validInfo == 'resume':
                    # print('lastResumeTime: ', self.lastResumeTime)
                # if validInfo == 'pause':
                    # print('lastPauseTime: ', self.lastPauseTime)
                # print("----------------------")
                if validInfo in ['setPosition', 'resume']:
                    self.setCurrentLrc(self.lastPosition)
                    self.outPutCurrentLrc()
                if validInfo == 'exit':
                    with open(self.outPut_path, 'w', encoding='utf-8') as outPutFile:
                        outPutFile.write('')
        return False

    def start(self, interval=0.001):
        """ Do a tail follow. If a callback function is registered it is called with every new line.
        Else # printed to standard out.

        Arguments:
            interval - Number of seconds to wait between each iteration; Defaults to 1. """
        file = self.monitor_path
        while True:
            _size = os.path.getsize(file)
            if _size < self.size:
                while self.try_count < 10:
                    if not self.reload_monitor_path():
                        self.try_count += 1
                    else:
                        self.try_count = 0
                        self.size = os.path.getsize(file)
                        break
                    time.sleep(0.1)

                if self.try_count == 10:
                    raise Exception("Open %s failed after try 10 times" % file)
            else:
                self.size = _size
            curr_position = self.file_.tell()
            line = self.file_.readline()
            if not line:
                self.file_.seek(curr_position)
            elif not line.endswith("\n"):
                self.file_.seed(curr_position)
            else:
                self.callback_log(line)
            time.sleep(interval)
            if self.playState == 1:
                self.setCurrentLrc()
                # outPutLrc = str(self.currentLrc) + '\n' + str(self.nextLrc)
                self.outPutCurrentLrc()

    def outPutCurrentLrc(self):
        currentL = strLrc(self.currentLrc['lrc'])
        currentTL = strLrc(self.currentLrc['tlrc'])
        nextL = strLrc(self.nextLrc['lrc'])
        nextTL = strLrc(self.nextLrc['tlrc'])

        outPutLrc = '<div class="lrc">' + currentL + '</div>' + \
                    '<div class="tlrc">' + currentTL + '</div>' + \
                    '<div class="lrc2">' + nextL + '</div>' + \
                    '<div class="tlrc2">' + nextTL + '</div>'
        if outPutLrc != self.outPutLrc:
            with open(self.outPut_path, 'w', encoding='utf-8') as outPutFile:
                outPutFile.write(outPutLrc)
            # print(self.nextLrc)
            self.outPutLrc = outPutLrc

    def check_file_validity(self):
        """ Check whether the a given file exists, readable and is a file.

            Arguments:
                file - the file path to be checked.
        """
        file = self.monitor_path
        if not os.path.isfile(file):
            # raise TailError("File '%s' does not exist" % (file))
            pass
        if not os.access(file, os.R_OK):
            # raise TailError("File '%s' not readable" % (file))
            pass
        if os.path.isdir(file):
            # raise TailError("File '%s' is a directory" % (file))
            pass

    def isContainNihonngo(self, source):
        p = re.compile('[\u0800-\u4e00]')
        searchResult = p.findall(source)
        # print(searchResult)
        searchResult = removeAll(searchResult, '一')
        # print(searchResult)
        if searchResult:
            return True
        return False

    def getLrc(self):
        def splitTimeLrc(lrcList):
            if lrcList is None:
                return None
            newList = dict()
            lrcList = re.split('\n', lrcList)
            for lrcItem in lrcList:
                lrcItem = re.split('\[(.*?)]', lrcItem)
                try:
                    lrcTime = lrcItem[1]
                    if 'by' in lrcTime:
                        continue
                    lrcTime = re.split(':', lrcTime)
                    M = int(lrcTime[0])
                    lrcTime = re.split('\.', lrcTime[1])
                    S = int(lrcTime[0])
                    ss = int(lrcTime[1])
                    lrcTime = M * 60 * 1000 + S * 1000 + ss
                    timeLrc = lrcItem[2]
                    if timeLrc == '':
                        continue
                    newList[lrcTime] = timeLrc
                except Exception as e:
                    pass
            return newList

        user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.87 Safari/537.36'
        headers = {'user-agent': user_agent}

        url = "http://music.163.com/api/song/lyric?id=" + str(self.currentSong) + "&lv=1&kv=1&tv=-1"
        jsonDate = requests.get(url, headers=headers)
        jsonDate = json.loads(jsonDate.text)
        # print('js---------\n', jsonDate, '\njs end--------------')
        result = dict()
        if 'nolyric' not in jsonDate.keys():
            try:
                lyric = jsonDate['lrc']['lyric']

            except KeyError:
                lyric = None
            try:
                translatedLyric = jsonDate['tlyric']['lyric']
            except KeyError:
                translatedLyric = None

            newL = splitTimeLrc(lyric)
            newTL = splitTimeLrc(translatedLyric)
            if newL is None:
                result[0] = {'lrc': '无歌词', 'tlrc': ''}
            else:
                for timeItem in newL:
                    l = newL[timeItem]
                    if self.isContainNihonngo(lyric):
                        l = l.replace(" ", "　")
                        lS = self.wakatiConv.do(l)
                        lSplitedList = lS.split(" ")
                        lConv = ""
                        for lSplited in lSplitedList:
                            if "　" in lSplited:
                                lSplited = lSplited.replace("　", "//split//　//split//")
                                lSplited = lSplited.split("//split//")
                            if isinstance(lSplited, list):
                                for item in lSplited:
                                    lSplitedH = self.kakasiConver(item, "H")
                                    if lSplitedH != item:
                                        tempList_lH = list(lSplitedH)
                                        tempList_l = list(item)
                                        end = list()
                                        for i in range(len(tempList_l)):
                                            if tempList_lH[-(i + 1)] == tempList_l[-(i + 1)]:
                                                end.append(tempList_l[-(i + 1)])
                                                tempList_lH[-(i + 1)] = ""
                                                tempList_l[-(i + 1)] = ""
                                            else:
                                                break
                                        removeAll(tempList_l, "")
                                        removeAll(tempList_lH, "")
                                        tempString = ""
                                        for string in tempList_l:
                                            tempString = tempString + string
                                        tempString = tempString + "("
                                        for string in tempList_lH:
                                            tempString = tempString + string
                                        tempString = tempString + ")"
                                        for string in end:
                                            tempString = tempString + string
                                    lConv = lConv + " " + item
                            else:
                                lSplitedH = self.kakasiConver(lSplited, "H")
                                lSplitedH = lSplitedH.replace(" ", "")
                                if lSplitedH != lSplited:
                                    tempList_lH = list(lSplitedH)
                                    tempList_l = list(lSplited)
                                    end = list()
                                    for i in range(len(tempList_l)):
                                        if tempList_lH[-(i+1)] == tempList_l[-(i+1)]:
                                            end.append(tempList_l[-(i+1)])
                                            tempList_lH[-(i+1)] = ""
                                            tempList_l[-(i+1)] = ""
                                        else:
                                            break
                                    removeAll(tempList_l, "")
                                    removeAll(tempList_lH, "")
                                    tempString = ""
                                    for string in tempList_l:
                                        tempString = tempString + string
                                    tempString = tempString + "("
                                    for string in tempList_lH:
                                        tempString = tempString + string
                                    tempString = tempString + ")"
                                    for string in end:
                                        tempString = tempString + string
                                    lSplited = tempString
                                lConv = lConv + " " + lSplited
                        lR = self.kakasiConver(l, "a")
                        l = lConv
                    if newTL is not None:
                        try:
                            tl = newTL[timeItem]
                        except KeyError:
                            tl = None
                    if self.isContainNihonngo(lyric):
                        if not tl is None:
                            tl = tl + "/" + lR
                        else:
                            tl = lR
                    result[timeItem] = {
                        'lrc': l,
                        'tlrc': tl
                    }

        else:
            url = 'https://music.163.com/api/song/detail/' \
                  '?id=' + str(self.currentSong) + '&ids=[' + str(self.currentSong) + ']'
            jsonDate = requests.get(url, headers=headers)
            jsonDate = json.loads(jsonDate.text)
            # print(jsonDate)
            songName = jsonDate['songs'][0]['name']
            artists = jsonDate['songs'][0]['artists']
            isStart = True
            for artist in artists:
                if isStart:
                    songArtist = 'by: ' + artist['name']
                    isStart = False
                else:
                    songArtist = songArtist + ' / ' + artist['name']
            # url2 = 'https://music.163.com//song?id=' + str(self.currentSong)
            # jsonDate2 = requests.get(url2, headers=headers)
            # pattern = r'data-res-name=".*"\ndata-res-author=".*"'
            # info = re.findall(pattern, jsonDate2.text)
            # songName = re.findall(r'data-res-name=".*?"', info[0])
            # songArtist = re.findall(r'data-res-author=".*?"', info[0])
            # songName = songName[0].replace('data-res-name="', '').replace('"', '')
            # songArtist = 'by: ' + songArtist[0].replace('data-res-author="', '').replace('"', '').replace('/', ' / ')
            result = {
                0: {'lrc': songName, 'tlrc': ''},
                999999999999: {'lrc': songArtist, 'tlrc': ''}
            }
        keyTime = list(result.keys())
        keyTime.sort()
        self.currentSongLrc = result
        self.songLrcKeyTime = keyTime

    def setCurrentLrc(self, targetTime=None):
        if targetTime is None:
            currentTime = time.time() - self.lastResumeTime + self.lastPosition
            if self.nextLrcTime is None:
                pass
            else:
                if currentTime*1000-500 >= self.nextLrcTime and self.playState == 1:
                    try:
                        self.currentLrc = self.nextLrc
                        currentLrcIndex = self.songLrcKeyTime.index(self.nextLrcTime)
                        self.currentLrcTime = self.songLrcKeyTime[currentLrcIndex]
                        if (len(self.songLrcKeyTime)-1) > currentLrcIndex:
                            self.nextLrcTime = self.songLrcKeyTime[currentLrcIndex+1]
                            self.nextLrc = self.currentSongLrc[self.nextLrcTime]
                        else:
                            self.nextLrcTime = None
                            self.nextLrc = {'lrc': '', 'tlrc': ''}
                    except Exception:
                        pass
        else:
            for timeItem in self.songLrcKeyTime:
                if timeItem >= targetTime*1000:
                    break
            try:
                timeIndex = self.songLrcKeyTime.index(timeItem)
                self.currentLrcTime = self.songLrcKeyTime[timeIndex - 1]
                if len(self.songLrcKeyTime) > 1:
                    self.nextLrcTime = self.songLrcKeyTime[timeIndex]
                    self.nextLrc = self.currentSongLrc[self.nextLrcTime]
                else:
                    self.nextLrcTime = None
                    self.nextLrc = {'lrc': '', 'tlrc': ''}
                self.currentLrc = self.currentSongLrc[self.currentLrcTime]
            except Exception as e:
                # print(e)
                pass

def removeAll(source, target):
    while target in source:
        source.remove(target)
    return source


if __name__ == '__main__':
    n = NeteaseMusicStatus()
    while True:
        try:
            n.start()
        except Exception as e:
            # print(e)
            n = NeteaseMusicStatus()
            pass
