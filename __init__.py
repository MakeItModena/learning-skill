from adapt.intent import IntentBuilder
from os.path import join, dirname, abspath, os, sys
from mycroft.messagebus.message import Message
from mycroft import intent_handler, intent_file_handler
from mycroft.filesystem import FileSystemAccess
from mycroft.audio import wait_while_speaking
from mycroft.skills.core import FallbackSkill
from mycroft.util.log import LOG, getLogger
from mycroft.util.parse import match_one
import re
from mycroft.skills.msm_wrapper import build_msm_config, create_msm
from msm import (
    MultipleSkillMatches,
    SkillNotFound,
)
import random

_author__ = 'gras64'

LOGGER = getLogger(__name__)


class LearningSkill(FallbackSkill):
    _msm = None #### From installer skill

    def __init__(self):
        super(LearningSkill, self).__init__("LearningSkill")
        self.privacy = ""
        self.catego = ""
        self.Category = ""

    def initialize(self):
        self.enable_fallback = self.settings.get('enable_fallback_ex') \
            if self.settings.get('enable_fallback_ex') is not None else True
        self.public_path = self.settings.get('public_path_ex') \
            if self.settings.get('public_path_ex') else self.file_system.path+"/public"
        self.local_path = self.settings.get('local_path_ex') \
            if self.settings.get('local_path_ex') else self.file_system.path+"/private"
        self.allow_category = self.settings.get('allow_category_ex') \
            if self.settings.get('allow_category_ex') else "humor,love,science"
        LOG.debug('local path enabled: %s' % self.local_path)
        self.saved_utt = ""
        if self.enable_fallback is True:
            self.register_fallback(self.handle_fallback, 6)
            self.register_fallback(self.handle_save_fallback, 99)
        LOG.debug('Learning-skil-fallback enabled: %s' % self.enable_fallback)

    def add_category(self, cat):
        path = self.file_system.path + "/category/"+ self.lang
        Category = self.get_response("add.category",
                                    data={"cat": cat})
        if not os.path.isdir(path):
            os.makedirs(path)
        save_category = open(path +"/"+ cat+'.voc', "w")
        save_category.write(cat)
        save_category.close()
        return True

    def _lines_from_path(self, path):
        with open(path, 'r') as file:
            lines = [line.strip().lower() for line in file]
            return lines

    def read_intent_lines(self, name, int_path):
        # self.speak(int_path)
        with open(self.find_resource(name + '.intent', int_path)) as f:
            # self.log.info('load intent: ' + f)
            return filter(bool, map(str.strip, f.read().split('\n')))

    def handle_fallback(self, message):
        utterance = message.data['utterance']
        if os.path.exists(self.public_path):
            path = self.public_path
            return self.load_fallback(utterance, path)
        if os.path.exists(self.local_path):
            path = self.local_path
            return self.load_fallback(utterance, path)

    def load_fallback(self, utterance, path):
            for f in os.listdir(path):
                int_path = path+"/"+f+"/"+"vocab"+"/"+self.lang
                try:
                    self.report_metric('failed-intent', {'utterance': utterance})
                except:
                    self.log.exception('Error reporting metric')

                for a in os.listdir(int_path):
                    i = a.replace(".intent", "")
                    for l in self.read_intent_lines(i, int_path):
                        if utterance.startswith(l):
                            self.log.debug('Fallback type: ' + i)
                            dig_path = path+"/"+f
                            e = join(dig_path, 'dialog', self.lang, i +'.dialog')
                            self.log.debug('Load Falback File: ' + e)
                            lines = open(e).read().splitlines()
                            i = random.choice(lines)
                            self.speak_dialog(i)
                            return True
                self.log.debug('fallback learning: ignoring')
            return False

    @intent_handler(IntentBuilder("HandleInteraction").require("Query").optionally("Something").
                    optionally("Private").require("Learning"))
    def handle_interaction(self, message, Category=None, saved_utt=None):
        private = message.data.get("Private", None)
        if private is None:
            privacy = self.public_path
            if Category is None:
                catego = self.get_response("begin.learning")
        else:
            privacy = self.local_path
            if Category is None:
                catego = self.get_response("begin.private")
        if Category is None:
            for cat in self.allow_category.split(","):
                try:
                    if self.voc_match(catego, cat):
                        Category = cat
                except:
                    self.add_category(cat)
            if Category is None:
                self.speak_dialog("invalid.category")
                return
        #privacy = self.public_path
        if saved_utt is None:
            question = self.get_response("question")
        else:
            self.log.info("become utt2"+saved_utt)
            question = saved_utt
            self.log.info("become utt"+question)

        if not question:
            self.log.info("stop")
            return  # user cancelled
        keywords = self.get_response("keywords")
        if not keywords:
            return  # user cancelled
        answer = self.get_response("answer")
        if not answer:
            return  # user cancelled
        confirm_save = self.ask_yesno(
            "save.learn",
            data={"question": question, "answer": answer})
        if confirm_save != "yes":
            self.log.debug('new knowledge rejected')
            return  # user cancelled
        answer_path = privacy+"/"+Category+"/"+"dialog"+"/"+self.lang
        question_path = privacy+"/"+Category+"/"+"vocab"+"/"+self.lang
        self.save_intent(question_path, question, keywords, answer_path, answer)

    def save_intent(self, question_path, question, keywords, answer_path=None, answer=None):
        if not answer_path is None:
            if not os.path.isdir(answer_path):
                os.makedirs(answer_path)
            save_dialog = open(answer_path+"/"+keywords.replace(" ", ".")+".dialog", "a")
            save_dialog.write(answer+"\n")
            save_dialog.close()
        if not os.path.isdir(question_path):
            os.makedirs(question_path)
        save_intent = open(question_path+"/"+keywords.replace(" ", ".")+".intent", "a")
        save_intent.write(question+"\n")
        save_intent.close()
        self.log.debug('new knowledge saved')

    def handle_save_fallback(self, message):
        self.saved_utt = message.data['utterance']
        self.log.info('save utterance for learning')

    @intent_file_handler('will_let_you_know.intent')
    def will_let_you_know_intent(self, message):
        catego = message.data.get("category")
        Category = None
        for cat in self.allow_category.split(","):
            try:
                if self.voc_match(catego, cat):
                    Category = cat
            except:
                self.add_category(cat)
        if not self.saved_utt is None:
            saved_utt = self.saved_utt
        else:
            saved_utt = None
        self.log.info("find Category: "+str(Category)+" and saved  utt: "+str(saved_utt))
        self.handle_interaction(message, Category, saved_utt)

    @intent_file_handler('something_for_my_skill.intent')
    def something_for_my_skill_intent(self, message):
        skill = self.find_skill(message.data['skill'], False)
        self.log.info("find Skill: "+str(skill))
        if not self.saved_utt is None:
            saved_utt = self.saved_utt
        self.scan_intent(skill)


    def scan_intent(self, skill):
        location = os.path.dirname(os.path.realpath(__file__))
        location = location + '/../'  # get skill parent directory path
        self.log.info("old uttr: "+str(self.saved_utt))
        self.speak_dialog("please.wait")
        for name in os.listdir(location):
            path = os.path.join(location, name)
            file = path.replace(location, '')
            if str(skill) in str(file):
                if os.path.isdir(path):
                #self.log.info('find skill folder: '+path)
                    for root, dirs, files in os.walk(str(path)):
                        for f in files:
                            #self.log.info('search file')
                            filename = os.path.join(root, f)
                            if filename.endswith('.intent'):
                                self.work_on_intent(filename, skill, location)

    def work_on_intent(self, filename, skill, location):
        #self.log.info('find intent file: '+filename)
        if self.lang in filename:
            fobj = open(filename)
            self.log.info('open intent file: '+filename)
            for line in fobj:
                match, confidence = match_one(self.saved_utt, [line])
                self.log.info('found intent: '+line.rstrip()+' '+str(confidence))
                if confidence > 0.5:
                    match, normal = self.normalise_question(match)
                    self.log.info('match '+str(confidence)+' found and normal '+normal)
                    if self.ask_yesno("do.you.mean", data={"match": normal}) is "yes":
                        fobj.close()
                        keywords = os.path.basename(filename).replace('.intent', '')
                        self.log.info('keywords: '+keywords)
                        question = self.saved_utt
                        question_path = self.file_system.path+"/skills/"+str(skill)+"/"+"vocab"+"/"+self.lang
                        self.log.info('bevor check: '+match)
                        question = self.check_question(question, match)
                        self.log.info('after check: '+match)
                        self.log.info('output question: '+match)
                        if self.ask_yesno("save.answer", data={"question": question, "skill": skill}) is "yes":
                            self.save_intent(question_path, question, keywords)
                        return
                    break
            fobj.close()

    def normalise_question(self, match):
        self.log.info('bevor filter : '+match)
        match = re.sub(r'(\|\s?\w+)','', match, flags=re.M) # select one for poodle (emty|full)
        match = re.sub(r'[()%]|(^\\.+)*|(^#+\s?.*)', '', match, flags=re.M) # for poodle
        match = re.sub(r'(#+\s?.*)|(^[,.: ]*)', '', match, flags=re.M)
        match = match.replace('|', ' ').replace('  ', ' ')
        normal = match
        normal = normal.replace('{', '').replace('}', '')
        self.log.info('make with: '+match+' normalise '+normal)
        return match, normal

    def check_question(self, question, match):
        self.log.info('bevor queston filter : '+match)
        match = match.replace('{{', '{').replace('}}', '}') ##small filter
        invariable = re.findall(r'({.*?})', match, flags=re.M)
        self.log.info('invariable : '+str(invariable))
        if invariable:
            for i in invariable:
                self.log.info('invariable schleife: '+str(i))
                outvariable = self.get_response("variable.found", data={"variable": i})
                question = question.replace(outvariable, '{'+i+'}')
        return question

    def find_skill(self, param, local): #### From installer skill
        """Find a skill, asking if multiple are found"""
        try:
            return self.msm.find_skill(param)
        except MultipleSkillMatches as e:
            skills = [i for i in e.skills if i.is_local == local]
            or_word = self.translate('or')
            if len(skills) >= 10:
                self.speak_dialog('error.too.many.skills')
                raise StopIteration
            names = [self.clean_name(skill) for skill in skills]
            if names:
                response = self.get_response(
                    'choose.skill', num_retries=0,
                    data={'skills': ' '.join([
                        ', '.join(names[:-1]), or_word, names[-1]
                    ])},
                )
                if not response:
                    raise StopIteration
                return self.msm.find_skill(response, skills=skills)
            else:
                raise SkillNotFound(param)

    @property #### From installer skill
    def msm(self):
        if self._msm is None:
            msm_config = build_msm_config(self.config_core)
            self._msm = create_msm(msm_config)

        return self._msm

    def shutdown(self):
        self.remove_fallback(self.handle_fallback)
        self.remove_fallback(self.handle_save_fallback)
        super(LearningSkill, self).shutdown()



def create_skill():
    return LearningSkill()
