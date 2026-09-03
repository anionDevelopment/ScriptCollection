import json
import os
import xml.etree.ElementTree as ET
from .GeneralUtilities import GeneralUtilities
from .ScriptCollectionCore import ScriptCollectionCore


class ARBTranslationHelper:
    """Reusable helper-functions for interacting with a Flutter-codeunit's ARB translation-files
    (lib/l10n/app_<locale>.arb) and with the XLIFF 2.0 files (Other/Resources/Translations/messages(.language).xlf)
    used to synchronize them. See ArbTranslationsOrganizer for the algorithm these are used by.
    """

    _XLIFF2_NAMESPACE = "urn:oasis:names:tc:xliff:document:2.0"
    _FILE_ID = "flutterl10n"

    @staticmethod
    def arb_file_path(arb_folder: str, language: str) -> str:
        # ARB-files use Dart's/Flutter's own locale-notation (underscore, e.g. "de_CH"), unlike the XLIFF-files below
        # (hyphen, e.g. "de-CH"), matching how ConSurvFrontend's messages.<language>.xlf are already named.
        return os.path.join(arb_folder, f"app_{language.replace('-', '_')}.arb")

    @staticmethod
    def base_xlf_file_path(xlf_folder: str) -> str:
        return os.path.join(xlf_folder, "messages.xlf")

    @staticmethod
    def xlf_file_path(xlf_folder: str, language: str) -> str:
        return os.path.join(xlf_folder, f"messages.{language}.xlf")

    @staticmethod
    def read_arb_messages(arb_file: str) -> dict[str, str]:
        """The message key/value pairs of an arb-file, skipping the "@@locale"-entry and any "@key"-metadata-entries.
        Returns an empty dict if the file does not exist."""
        if not os.path.isfile(arb_file):
            return {}
        with open(arb_file, "r", encoding="utf-8") as f:
            content: dict = json.load(f)
        return {key: value for key, value in content.items() if not key.startswith("@")}

    @staticmethod
    def write_arb_messages(arb_file: str, language: str, template_keys: list[str], messages: dict[str, str]) -> None:
        """Writes an arb-file containing "@@locale" plus one entry per key of template_keys which has a value in
        messages (in that same order, so the file stays diffable against the template arb-file, and so a message-key
        which is not part of template_keys is dropped)."""
        content = {"@@locale": language.replace("-", "_")}
        for key in template_keys:
            if key in messages:
                content[key] = messages[key]
        with open(arb_file, "w", encoding="utf-8", newline="\n") as f:#newline="\n": arb-files use LF line-endings; without this, Python would translate "\n" to the OS default (CRLF on Windows).
            json.dump(content, f, ensure_ascii=False, indent=2)
            f.write("\n")

    @classmethod
    def read_effective_messages(cls, xlf_file: str) -> dict[str, str]:
        """For every <unit> of an XLIFF-file: its <target>-text if its segment has one, otherwise its <source>-text
        (i.e. the value this message currently effectively has, translated or not). Returns an empty dict if the file
        does not exist yet."""
        if not os.path.isfile(xlf_file):
            return {}
        ns = {"x": cls._XLIFF2_NAMESPACE}
        messages: dict[str, str] = {}
        for unit in ET.parse(xlf_file).getroot().findall(".//x:unit", ns):
            segment = unit.find("x:segment", ns)
            if segment is None:
                continue
            target = segment.find("x:target", ns)
            source = segment.find("x:source", ns)
            text = target.text if target is not None and target.text else (source.text if source is not None else None)
            if text is not None:
                messages[unit.get("id")] = text
        return messages

    @classmethod
    def build_unit(cls, unit_id: str, source: str, target: str | None) -> ET.Element:
        """An XLIFF <unit> with the given id and source-text; state="translated" with the given <target> if target is
        given, otherwise state="initial" without a <target>."""
        unit = ET.Element(f"{{{cls._XLIFF2_NAMESPACE}}}unit", {"id": unit_id})
        segment = ET.SubElement(unit, f"{{{cls._XLIFF2_NAMESPACE}}}segment")
        ET.SubElement(segment, f"{{{cls._XLIFF2_NAMESPACE}}}source").text = source
        if target is None:
            segment.set("state", "initial")
        else:
            segment.set("state", "translated")
            ET.SubElement(segment, f"{{{cls._XLIFF2_NAMESPACE}}}target").text = target
        return unit

    @classmethod
    def write_xliff2_file(cls, file: str, src_lang: str, trg_lang: str | None, units: list[ET.Element]) -> None:
        """(Over)writes an XLIFF 2.0 file at "file" from scratch, containing exactly the given units."""
        ET.register_namespace("", cls._XLIFF2_NAMESPACE)
        attributes = {"version": "2.0", "srcLang": src_lang}
        if trg_lang is not None:
            attributes["trgLang"] = trg_lang
        root = ET.Element(f"{{{cls._XLIFF2_NAMESPACE}}}xliff", attributes)
        file_element = ET.SubElement(root, f"{{{cls._XLIFF2_NAMESPACE}}}file", {"id": cls._FILE_ID, "original": "app_en.arb"})
        for unit in units:
            file_element.append(unit)
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        with open(file, "wb") as f:#binary mode (as opposed to passing the filename directly to tree.write): guarantees LF line-endings regardless of the OS' default line-ending, since binary mode never translates "\n" to "\r\n".
            tree.write(f, encoding="utf-8", xml_declaration=True)


class ArbTranslationsOrganizer:
    """Synchronizes a codeunit's ARB translation-files (lib/l10n/app_<locale>.arb) with XLIFF 2.0 files
    (messages(.language).xlf), so both stay consistent. This type makes no assumption about which kind of codeunit
    calls it or where its files live within that codeunit - it only operates on the given, already-resolved
    "arb_folder"/"xlf_folder" paths and the given ScriptCollectionCore instance (used for the actual xlf-sync, see
    ScriptCollectionCore.sync_xlf2_files); a caller like TFCPS_CodeUnitSpecific_Flutter_Functions.organize_translations()
    resolves those paths from its own codeunit-folder-conventions first.
    """

    BaseLanguage="en"#"en" means en-US; this is also why "en-GB" is allowed to be contained in "languages" further down.

    def organize_translations(self,sc:ScriptCollectionCore,arb_folder:str,xlf_folder:str,languages:list[str])->dict[str,dict[int,float]]:#languages look like ["fr","de","es","de-CH","en-GB"]; "en" is not contained because en is always the default language.
        #after this functions all texts in the arb files should be in the xlf files, and all texts in the xlf files should be in the arb files. see algorithm below
        #in general: arb_en.arb is the source of the truth regarding to which texts exist and the source of truh for the english texts.
        #returns the translation-state-statistics of the xlf-files (not of the arb-files), see ScriptCollectionCore.sync_xlf2_files.
        GeneralUtilities.assert_folder_exists(arb_folder)
        GeneralUtilities.ensure_directory_exists(xlf_folder)

        self.__ensure_arb_files_exist(arb_folder,languages)
        self.__ensure_xlf_files_exist(arb_folder,xlf_folder,languages)
        self.__clean_up_arb_files(arb_folder,languages)
        self.__write_arb_entries_to_xlf_files(arb_folder,xlf_folder)
        statistics=self.__sync_xlf_files(sc,xlf_folder,languages)
        self.__sync_xlf_files_to_arb_files(arb_folder,xlf_folder,languages)
        return statistics

    def __ensure_arb_files_exist(self,arb_folder:str,languages:list[str]):
        #after this function in arb_folder should be a arb-file for each language in languages. create the file if not already exist.
        for language in languages:
            arb_file=ARBTranslationHelper.arb_file_path(arb_folder,language)
            if not os.path.isfile(arb_file):
                ARBTranslationHelper.write_arb_messages(arb_file,language,[],{})

    def __ensure_xlf_files_exist(self,arb_folder:str,xlf_folder:str,languages:list[str]):
        #after this function in xlf_folder should be a xlf-file for each language in languages. create the file if not already exist.
        #a newly created file is bootstrapped from the language's current arb-translations (not left empty/untranslated), so translation-work already done directly in the arb-file (as it is right now for de/fr/es) is not discarded once that language starts taking part in the xlf-side of the sync.
        english_messages=ARBTranslationHelper.read_arb_messages(ARBTranslationHelper.arb_file_path(arb_folder,self.BaseLanguage))
        for language in languages:
            xlf_file=ARBTranslationHelper.xlf_file_path(xlf_folder,language)
            if os.path.isfile(xlf_file):
                continue
            arb_messages=ARBTranslationHelper.read_arb_messages(ARBTranslationHelper.arb_file_path(arb_folder,language))
            units=[ARBTranslationHelper.build_unit(key,value,arb_messages.get(key)) for key,value in english_messages.items()]
            ARBTranslationHelper.write_xliff2_file(xlf_file,self.BaseLanguage,language,units)

    def __clean_up_arb_files(self,arb_folder:str,languages:list[str]):
        #after this function all arb files should only contain message-keys which are contained in app_en.arb. (texts which are not in app_en.arb anymore should be removed in the other arb files)
        template_keys=list(ARBTranslationHelper.read_arb_messages(ARBTranslationHelper.arb_file_path(arb_folder,self.BaseLanguage)).keys())
        for language in languages:
            arb_file=ARBTranslationHelper.arb_file_path(arb_folder,language)
            ARBTranslationHelper.write_arb_messages(arb_file,language,template_keys,ARBTranslationHelper.read_arb_messages(arb_file))

    def __write_arb_entries_to_xlf_files(self,arb_folder:str,xlf_folder:str):
        #after this function all texts from arb_en.arb should be in messages.xlf (do not touch other files than this both in the other steps) replace the entire message content of all entries in xlf. arb_en.arb defines all "true" entries and this is the only source of truth. so messages.xlf should contain these and only these entries. simple algorithm: remove the entire content from messages.xlf, then for each entry in arb_en.arb create a new entry in messages.xlf with the same message-key and the same message-value.
        english_messages=ARBTranslationHelper.read_arb_messages(ARBTranslationHelper.arb_file_path(arb_folder,self.BaseLanguage))
        units=[ARBTranslationHelper.build_unit(key,value,None) for key,value in english_messages.items()]
        ARBTranslationHelper.write_xliff2_file(ARBTranslationHelper.base_xlf_file_path(xlf_folder),self.BaseLanguage,None,units)

    def __sync_xlf_files(self,sc:ScriptCollectionCore,xlf_folder:str,languages:list[str])->dict[str,dict[int,float]]:
        #sync xlf-files. after this function the xlf files should be synchronized in that way that all xlf-files do have all values, does not matter if translated or untranslated (even if the xlf file for other languages than english should state it if a text is not translated in the usual way it is stated in xlf files). also ensure that the messages.<language>.xlf files do not have message-keys which are not contained in messages.xlf
        return sc.sync_xlf2_files("messages",languages,xlf_folder)

    def __sync_xlf_files_to_arb_files(self,arb_folder:str,xlf_folder:str,languages:list[str]):
        #for each "messages.<language>.xlf"-xlf-file (means: for all xlf files other than messages.xlf): for each message-key: write the message-value to the corresponding arb-file in arb_folder. overwrite any existing value in the corresponding arb-file.
        template_keys=list(ARBTranslationHelper.read_arb_messages(ARBTranslationHelper.arb_file_path(arb_folder,self.BaseLanguage)).keys())
        for language in languages:
            effective_messages=ARBTranslationHelper.read_effective_messages(ARBTranslationHelper.xlf_file_path(xlf_folder,language))
            ARBTranslationHelper.write_arb_messages(ARBTranslationHelper.arb_file_path(arb_folder,language),language,template_keys,effective_messages)
