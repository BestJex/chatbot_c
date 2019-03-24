# coding=utf-8
import math

import jieba
import jieba.analyse
import time
from interrogative.api import *
from gensim import corpora, models, similarities
from function import exponential_decay
from db_connect import connect_mongodb_col
from corpora_processing import extract_tf_idf, produce_addwordlist, load_addwordlist, sentence_similarity
from theme_bot import ThemeBot
from theme_ques_bot import ThemeQuesBot


class ChatBot:
    """
    主机器人,负责调用管理主题机器人，使其完成任务
    """
    dbname = 'chatbotdb'
    themebot_col_name = 'themebot'
    userdict_path = 'corpus/dict.txt'

    def __init__(self):
        jieba.load_userdict(ChatBot.userdict_path)
        themebot_col = connect_mongodb_col(ChatBot.dbname, ChatBot.themebot_col_name)
        self.themes = []
        self.themebots = {}
        self.themequesbots = {}
        for item in themebot_col.find({}, {'_id': 0}):
            self.themes.append(item['theme'])
        load_addwordlist()

    def extract_dict(self):
        """
        读取所有theme对应的文档内容
        对内容进行分词并计算tf-idf值
        :return:
        """
        print('开始分词并计算tf-idf值')
        row_corpus = []
        for theme in self.themes:
            theme_col = connect_mongodb_col(ChatBot.dbname, theme + '_doc')
            for item in theme_col.find({}, {'title': 1, 'content': 1}):
                row_corpus.append(item['title'].lower() + item['content'].lower())
        extract_tf_idf(row_corpus)
        print('成功获得字典')

    def extract_addword(self):
        """
        选取所有theme对应的类别内容
        对类别进行分词得到附加词表
        并将存入tf_idf字典中
        :return:
        """
        types = []
        themebot_col = connect_mongodb_col(ChatBot.dbname, ChatBot.themebot_col_name)
        for item in themebot_col.find({}, {'_id': 0}):
            types.append(item['theme'] + item['types'])
        produce_addwordlist(types)
        print('附加词生成成功!')

    def theme_bot_start(self, theme, train=False):
        """
        启动一个主题机器人
        :param theme:
        :param train:
        :return:
        """
        if theme not in self.themes:
            print(theme + '_bot 不存在,启动失败!')
            return
        bot = ThemeBot(theme)
        bot.start(train)
        print(theme + '_bot 启动成功!')
        return bot

    def theme_ques_bot_start(self, theme, train=False):
        """
        启动一个主题问题机器人
        :param theme:
        :param train:
        :return:
        """
        if theme not in self.themes:
            print(theme + '_bot 不存在,启动失败!')
            return
        bot = ThemeQuesBot(theme)
        bot.start(train)
        print(theme + '_ques_bot 启动成功!')
        return bot

    def retrain_all_bots(self):
        """
        重新训练所有themebot
        :return:
        """
        # 重新生成语料
        self.extract_dict()
        temp_theme_bot = {}
        temp_ques_theme_bot = {}
        for theme in self.themes:
            bot = self.theme_bot_start(theme, train=True)
            temp_theme_bot[theme] = bot
            ques_bot = self.theme_ques_bot_start(theme, train=True)
            temp_ques_theme_bot[theme] = ques_bot
        self.themebots = temp_theme_bot
        self.themequesbots = temp_ques_theme_bot
        print('所有themebot训练成功!')

    def start_all_bots(self):
        """
        启动所有的主题机器人
        :return:
        """
        temp_theme_bot = {}
        temp_ques_theme_bot = {}
        for theme in self.themes:
            bot = self.theme_bot_start(theme, train=False)
            temp_theme_bot[theme] = bot
            ques_bot = self.theme_ques_bot_start(theme, train=False)
            temp_ques_theme_bot[theme] = ques_bot
        self.themebots = temp_theme_bot
        self.themequesbots = temp_ques_theme_bot
        print('所有themebot启动成功!')

    def similar_theme_matching(self, target, theme_num=3):
        """
        根据传入的语句进行分词，然后与各个主题机器人进行关键词比较
        选取更相似的前theme_num个主题机器人进行匹配
        :param tatget:
        :return:
        """
        target_key_words = jieba.cut(target)
        theme_dict = {}
        for theme in self.themes:
            num = 0
            for word in target_key_words:
                if word in self.themebots[theme].key_words:
                    num = num + 1
            if num != 0:
                theme_dict[theme] = num
        if len(theme_dict) == 0:
            return self.themes
        else:
            print(theme_dict)
            return theme_dict.keys()

    def similar_documents(self, target, themes):
        """
        传入目标问题和主题名，调用对应机器人的相似文档匹配函数
        :param themes:
        :return:
        """
        # 判断是否是疑问句
        taglist = jieba.cut(target)
        tag = recognize(' '.join(taglist))
        print('tag:', tag)
        if tag:
            docs = []
            ques_docs = []
            # 相似文档匹配
            for theme in themes:
                list = self.themebots[theme].get_similar_documents(target)
                if list is None:
                    continue
                for l in list:
                    if float(l[1]) > 0.3:
                        docs.append(l)
            # 相似问题匹配
            for theme in themes:
                list = self.themequesbots[theme].get_similar_questions(target)
                if list is None:
                    continue
                for l in list:
                    if float(l[1]) > 0.3:
                        ques_docs.append(l)
            for doc in docs:
                doc[1] = float(doc[1]) + sentence_similarity(target, doc[0])
            for ques_doc in ques_docs:
                ques_doc[1] = float(ques_doc[1]) + sentence_similarity(target, ques_doc[0])
            # 相似文档排序
            sort_docs = sorted(docs, key=lambda x: x[1], reverse=True)[:5]
            # 相似问题排序
            sort_ques_docs = sorted(ques_docs, key=lambda x: x[1], reverse=True)[:5]
            # 重新排列
            resort_docs = sorted(sort_ques_docs + sort_docs,key=lambda x: x[1], reverse=True)
            return resort_docs
        else:
            docs = []
            # 相似文档匹配
            for theme in themes:
                list = self.themebots[theme].get_similar_documents(target)
                if list is None:
                    continue
                for l in list:
                    if float(l[1]) > 0.3:
                        docs.append(l)
            for doc in docs:
                doc[1] = float(doc[1]) + sentence_similarity(target, doc[0])
            # 相似文档排序
            sort_docs = sorted(docs, key=lambda x: x[1], reverse=True)
            return sort_docs[:10]

    def similar_recommanded(self, user, recommended_num=20, theme_num=3):
        """
        传入用户名和主题名，获取其历史记录，获得历史权重值，筛选出比重高的主题
        将历史记录传入对应的ThemeBot，获得相似文档的推荐集合
        :param themes:
        :return:
        """
        colname = 'history'
        col = connect_mongodb_col(ChatBot.dbname, colname)
        history = [item for item in col.find({'user': user}, {'_id': 0, 'user': 0}).sort('time', -1).limit(50)]
        # 初始化历史权重字典
        weight_dict = {theme: 0 for theme in self.themes}
        # 初始化历史记录字典，用于将历史记录按theme分类
        record_dict = {theme: [] for theme in self.themes}
        # 读取当前时间
        now = time.time()
        # 一天的时间戳值
        day_value = 86400
        for item in history:
            # 转为时间数组
            timeArray = time.strptime(item['time'], "%Y-%m-%d %H:%M:%S")
            # 转为时间戳
            timeStamp = int(time.mktime(timeArray))
            diff_value = math.floor((now - timeStamp) / day_value)
            # 计算历史权重
            item['decay'] = exponential_decay(diff_value)
            weight_dict[item['theme']] += exponential_decay(diff_value)
            record_dict[item['theme']].append(item)
        print(weight_dict)
        theme_list = sorted(weight_dict, key=weight_dict.get, reverse=True)
        weight_sum = 0
        print('record_doct', record_dict)
        for theme in record_dict.keys():
            print(record_dict[theme])
        # 计算权重和
        for theme in theme_list:
            weight_sum += weight_dict[theme]
        # 获取推荐集合
        recommended_list = []
        for theme in theme_list:
            record_num = math.floor(recommended_num * weight_dict[theme] / weight_sum)
            if record_num > 0:
                recommended_list.append(self.themebots[theme].historical_recommanded(record_dict[theme], record_num))
        return recommended_list


def main():
    chatbot = ChatBot()
    chatbot.start_all_bots()
    chatbot.similar_recommanded(user='lym')
    """
    while True:
        target = input('->')
        chatbot.similar_documents(target, chatbot.similar_theme_matching(target))
    """


if __name__ == '__main__':
    main()
