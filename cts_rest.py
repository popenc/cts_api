"""
CTS workflow/module-oriented REST endpoints

For Chemical Editor, p-chem table, chemical speciation,
and reaction pathways.
"""

import logging
import json
import datetime
import pytz

from django.http import HttpResponse, HttpRequest
from django.template.loader import render_to_string
from django.shortcuts import render_to_response

from ..cts_calcs.calculator_chemaxon import JchemCalc
from ..cts_calcs.calculator_epi import EpiCalc
from ..cts_calcs.calculator_measured import MeasuredCalc
from ..cts_calcs.calculator_test import TestCalc
from ..cts_calcs.calculator_test import TestWSCalc
from ..cts_calcs.calculator_sparc import SparcCalc
from ..cts_calcs.calculator_metabolizer import MetabolizerCalc
from ..models.chemspec import chemspec_output  # todo: have cts_calcs handle specation, sans chemspec output route
from ..cts_calcs.calculator import Calculator
from ..cts_calcs import smilesfilter



# TODO: Consider putting these classes somewhere else, maybe even the *_models.py files!
class Molecule(object):
	"""
	Basic molecule object for CTS
	"""
	def __init__(self):

		# cts keys:
		self.chemical = ''  # initial structure from user (any chemaxon format)
		self.orig_smiles = ''  # before filtering, converted to smiles

		# chemaxon/jchem keys:
		self.smiles = ''  # post filtered smiles 
		self.formula = ''
		self.iupac = ''
		self.cas = ''
		self.mass = ''
		self.structureData = ''
		self.exactMass = ''

	def createMolecule(self, chemical, orig_smiles, chem_details_response, get_structure_data=None):
		"""
		Gets Molecule attributes from Calculator's getChemDetails response
		"""

		logging.warning("STRUCTURE DATA: {}".format(get_structure_data))

		try:
			# set attrs from jchem data:
			for key in self.__dict__.keys():
				# if key == 'structureData' and structureData:
				# 	self.__setattr__(key, chem_details_response['data'][0])

				# get_sd = key == 'structureData' and get_structure_data != None
				# logging.warning("KEY: {}, BOOL: {}".format(key, get_sd))

				if key != 'orig_smiles' and key != 'chemical':
					logging.warning("elif key: {}".format(key))
					if key == 'structureData' and get_structure_data == None:
						pass
					elif key == 'cas':
						# check if object with 'error' key instead of string of CAS#..
						if isinstance(chem_details_response['data'][0][key], dict):
							self.__setattr__(key, "N/A")
						else:
							self.__setattr__(key, chem_details_response['data'][0][key])	
					else:
						self.__setattr__(key, chem_details_response['data'][0][key])
			# set cts attrs:
			self.__setattr__('chemical', chemical)
			self.__setattr__('orig_smiles', orig_smiles)

			return self.__dict__
		except KeyError as err:
			raise err


class CTS_REST(object):
	"""
	CTS level endpoints for REST API.
	Will have subclasses for calculators and
	other CTS features, like metabolizer.
	"""
	def __init__(self):
		self.calcs = ['chemaxon', 'epi', 'test', 'sparc', 'measured']
		self.endpoints = ['cts', 'metabolizer'] + self.calcs
		self.meta_info = {
			'metaInfo': {
				'model': "cts",
				'collection': "qed",
				'modelVersion': "1.3.22",
				'description': "The Chemical Transformation System (CTS) was generated by researchers at the U.S. Enivornmental Protection Agency to provide access to a collection of physicochemical properties and reaction transformation pathways.",
				'status': '',
				'timestamp': gen_jid(),
				'url': {
					'type': "application/json",
					'href': "http://qedinternal.epa.gov/cts/rest"
				}
			},
		}
		self.links = [
			{
				'rel': "episuite",
				'type': "application/json",
				'href': "http://qedinternal.epa.gov/cts/rest/episuite"
			},
			{
				'rel': "chemaxon",
				'type': "application/json",
				'href': "http://qedinternal.epa.gov/cts/rest/chemaxon"
			},
			{
				'rel': "sparc",
				'type': "application/json",
				'href': "http://qedinternal.epa.gov/cts/rest/sparc"
			},
			{
				'rel': "test",
				'type': "application/json",
				'href': "http://qedinternal.epa.gov/cts/rest/test"
			},
			{
				'rel': "metabolizer",
				'type': "application/json",
				'href': "http://qedinternal.epa.gov/cts/rest/metabolizer"
			}
		]
		self.calc_links = [
			{
				'rel': "inputs",
				'type': "application/json",
				'href': "http://qedinternal.epa.gov/cts/rest/{}/inputs",
				'description': "ChemAxon input schema",
				'method': "POST",
			},
			{
				'rel': "outputs",
				'type': "application/json",
				'href': "http://qedinternal.epa.gov/cts/rest/{}/outputs",
				'description': "ChemAxon output schema",
				'method': "POST"
			},
			{
				'rel': "run",
				'type': "application/json",
				'href': "http://qedinternal.epa.gov/cts/rest/{}/run",
				'description': "ChemAxon estimated values",
				'method': "POST"
			}
		]
		self.pchem_inputs = ['chemical', 'calc', 'prop', 'run_type']
		self.metabolizer_inputs = ['structure', 'generationLimit', 'transformationLibraries']

	@classmethod
	def getCalcObject(self, calc):
		if calc == 'cts':
			return CTS_REST()
		elif calc == 'chemaxon':
			return Chemaxon_CTS_REST()
		elif calc == 'epi':
			return EPI_CTS_REST()
		elif calc == 'test':
			return TEST_CTS_REST()
		elif calc == 'testws':
			return TEST_CTS_REST()
		elif calc == 'sparc':
			return SPARC_CTS_REST()
		elif calc == 'measured':
			return Measured_CTS_REST()
		elif calc == 'metabolizer':
			return Metabolizer_CTS_REST()
		else:
			return None

	def getCalcLinks(self, calc):
		if calc in self.calcs:
			_links = self.calc_links
			for item in _links:
				if 'href' in item:
					item['href'] = item['href'].format(calc)  # insert calc name into href
			return _links
		else:
			return None

	def getCTSREST(self):
		_response = self.meta_info
		_response['links'] = self.links
		return HttpResponse(json.dumps(_response), content_type='application/json')

	def getCalcEndpoints(self, calc):
		_response = {}
		calc_obj = self.getCalcObject(calc)
		_response.update({
			'metaInfo': calc_obj.meta_info,
			'links': self.getCalcLinks(calc)
		})
		return HttpResponse(json.dumps(_response), content_type="application/json")

	def getCalcInputs(self, chemical, calc, prop=None):
		_response = {}
		calc_obj = self.getCalcObject(calc)
		
		_response.update({'metaInfo': calc_obj.meta_info})

		if calc in self.calcs:
			_response.update({
			'inputs': {
				'chemical': chemical,
				'prop': prop,
				'calc': calc,
				'run_type': "rest",
			}
		})
		elif calc == 'metabolizer':
			_response.update({
				'inputs': calc_obj.inputs
			})
		return HttpResponse(json.dumps(_response), content_type="application/json")

	def runCalc(self, calc, request_dict):

		_response = {}
		_response = self.meta_info

		if calc == 'metabolizer':
			structure = request_dict.get('structure')
			gen_limit = request_dict.get('generationLimit')
			trans_libs = request_dict.get('transformationLibraries')

			# TODO: Add transformationLibraries key:val logic
			metabolizer_request = {
				'structure': structure,
				'generationLimit': gen_limit,
				'populationLimit': 0,
				'likelyLimit': 0.001,
				# 'transformationLibraries': trans_libs,
				'excludeCondition': ""  # 'generateImages': False
			}


			# metabolizerList = ["hydrolysis", "abiotic_reduction", "human_biotransformation"]
			# NOTE: Only adding 'transformationLibraries' key:val if hydrolysis and/or reduction selected, but not mammalian metabolism
			if len(trans_libs) > 0 and not 'human_biotransformation' in trans_libs:
				metabolizer_request.update({'transformationLibraries': trans_libs})

			try:
				response = MetabolizerCalc().getTransProducts(metabolizer_request)
			except Exception as e:
				logging.warning("error making data request: {}".format(e))
				raise

			_progeny_tree = MetabolizerCalc().recursive(response, int(gen_limit))
			_response.update({'data': json.loads(_progeny_tree)})

		elif calc == 'speciation':
			# response = getChemicalSpeciationData(request)
			# _response.update({'data': json.loads(response.content)})

			logging.info("CTS REST - speciation")

			return getChemicalSpeciationData(request_dict)

		else:

			try:

				logging.warning("REQUEST DICT TYPE: {}".format(type(request_dict)))

				_orig_smiles = request_dict.get('chemical')
				logging.info("ORIG SMILES: {}".format(_orig_smiles))
				_filtered_smiles = smilesfilter.filterSMILES(_orig_smiles)['results'][-1]
				request_dict.update({
					'orig_smiles': _orig_smiles,
					'chemical': _filtered_smiles,
				})
			except AttributeError as ae:
				# POST type is django QueryDict (most likely)
				request_dict = dict(request_dict)  # convert QueryDict to dict
				for key, val in request_dict.items():
					request_dict.update({key: val[0]})  # vals of QueryDict are lists of 1 item

				request_dict.update({
					'orig_smiles': _orig_smiles,
					'chemical': _filtered_smiles,
				})
			except Exception as e:
				logging.warning("exception in cts_rest.py runCalc: {}".format(e))
				logging.warning("skipping SMILES filter..")

			pchem_data = {}
			if calc == 'chemaxon':
				pchem_data = JchemCalc().data_request_handler(request_dict)
				# logging.warning("PCHEM DATA: {}".format(pchem_data))
			elif calc == 'epi':
				pchem_data = EpiCalc().data_request_handler(request_dict)
			elif calc == 'test':
				pchem_data = TestCalc().data_request_handler(request_dict)
			elif calc == 'testws':
				pchem_data = TestWSCalc().data_request_handler(request_dict)
			elif calc == 'sparc':
				pchem_data = SparcCalc().data_request_handler(request_dict)
			elif calc == 'measured':
				pchem_data = MeasuredCalc().data_request_handler(request_dict)
				# with updated measured, have to pick out desired prop:
				for data_obj in pchem_data.get('data'):
					measured_prop_name = MeasuredCalc().propMap[request_dict['prop']]['result_key']
					if data_obj['prop'] == measured_prop_name:
						pchem_data['data'] = data_obj['data'] # only want request prop
						pchem_data['prop'] = request_dict['prop']  # use cts prop name
			
			_response.update({'data': pchem_data})

		return HttpResponse(json.dumps(_response), content_type="application/json")



class Chemaxon_CTS_REST(CTS_REST):
	"""
	CTS REST endpoints, etc. for ChemAxon
	"""
	def __init__(self):
		self.meta_info = {
			'metaInfo': {
				'model': "chemaxon",
				'collection': "qed",
				'modelVersion': "Jchem Web Services 15.3.23.0",
				'description': "Cheminformatics software platforms, applications, and services to optimize the value of chemistry information in life science and other R&D.",
				'status': '',
				'timestamp': gen_jid(),
				'url': {
					'type': "application/json",
					'href': "http://qedinternal.epa.gov/cts/rest/chemaxon"
				},
				'props': ['water_sol', 'ion_con', 'kow_no_ph', 'kow_wph'],
				'availableProps': [
					{
						'prop': 'water_sol',
						'units': 'mg/L',
						'description': "water solubility"
					},
					{
						'prop': 'ion_con',
						'description': "pKa and pKa values"
					},
					{
						'prop': 'kow_no_ph',
						'units': "log",
						'description': "Octanol/water partition coefficient",
						'methods': ['KLOP', 'PHYS', 'VG']
					},
					{
						'prop': 'kow_wph',
						'units': "log",
						'description': "pH-dependent octanol/water partition coefficient",
						'methods': ['KLOP', 'PHYS', 'VG']
					}
				]
			}
		}


class EPI_CTS_REST(CTS_REST):
	"""
	CTS REST endpoints, etc. for EPI Suite
	"""
	def __init__(self):
		self.meta_info = {
			'metaInfo': {
				'model': "epi",
				'collection': "qed",
				'modelVersion': "4.11",
				'description': "EPI Suite is a Windows-based suite of physical/chemical property and environmental fate estimation programs developed by EPA and Syracuse Research Corp. (SRC).",
				'status': '',
				'timestamp': gen_jid(),
				'url': {
					'type': "application/json",
					'href': "http://qedinternal.epa.gov/cts/rest/epi"
				},
				'availableProps': [
					{
						'prop': 'melting_point',
						'units': 'degC',
						'description': "melting point"
					},
					{
						'prop': 'boiling_point',
						'units': 'degC',
						'description': "boiling point"
					},
					{
						'prop': 'water_sol',
						'units': 'mg/L',
						'description': "water solubility"
					},
					{
						'prop': 'vapor_press',
						'units': 'mmHg',
						'description': "vapor pressure"
					},
					{
						'prop': 'henrys_law_con',
						'units': '(atm*m^3)/mol',
						'description': "henry's law constant"
					},
					{
						'prop': 'kow_no_ph',
						'units': "log",
						'description': "Octanol/water partition coefficient"
					},
					{
						'prop': 'koc',
						'units': "L/kg",
						'description': "organic carbon partition coefficient"
					}
				]
			}
		}


class TEST_CTS_REST(CTS_REST):
	"""
	CTS REST endpoints, etc. for EPI Suite
	"""
	def __init__(self):
		self.meta_info = {
			'metaInfo': {
				'model': "test",
				'collection': "qed",
				'modelVersion': "4.2.1",
				'description': "The Toxicity Estimation Software Tool (TEST) allows users to easily estimate the toxicity of chemicals using QSARs methodologies.",
				'status': '',
				'timestamp': gen_jid(),
				'url': {
					'type': "application/json",
					'href': "http://qedinternal.epa.gov/cts/rest/test"
				},
				'availableProps': [
					{
						'prop': 'melting_point',
						'units': 'degC',
						'description': "melting point",
						'method': "FDAMethod"
					},
					{
						'prop': 'boiling_point',
						'units': 'degC',
						'description': "boiling point",
						'method': "FDAMethod"
					},
					{
						'prop': 'water_sol',
						'units': 'mg/L',
						'description': "water solubility",
						'method': "FDAMethod"
					},
					{
						'prop': 'vapor_press',
						'units': 'mmHg',
						'description': "vapor pressure",
						'method': "FDAMethod"
					}
				]
			}
		}


class SPARC_CTS_REST(CTS_REST):
	"""
	CTS REST endpoints, etc. for EPI Suite
	"""
	def __init__(self):
		self.meta_info = {
			'metaInfo': {
				'model': "sparc",
				'collection': "qed",
				'modelVersion': "",
				'description': "SPARC Performs Automated Reasoning in Chemistry (SPARC) is a chemical property estimator developed by UGA and the US EPA",
				'status': '',
				'timestamp': gen_jid(),
				'url': {
					'type': "application/json",
					'href': "http://qedinternal.epa.gov/cts/rest/sparc"
				},
				'availableProps': [
					{
						'prop': 'boiling_point',
						'units': 'degC',
						'description': "boiling point"
					},
					{
						'prop': 'water_sol',
						'units': 'mg/L',
						'description': "water solubility"
					},
					{
						'prop': 'vapor_press',
						'units': 'mmHg',
						'description': "vapor pressure"
					},
					{
						'prop': 'mol_diss',
						'units': 'cm^2/s',
						'description': "molecular diffusivity"
					},
					{
						'prop': 'ion_con',
						'description': "pKa and pKa values"
					},
					{
						'prop': 'henrys_law_con',
						'units': '(atm*m^3)/mol',
						'description': "henry's law constant"
					},
					{
						'prop': 'kow_no_ph',
						'units': "log",
						'description': "octanol/water partition coefficient"
					},
					{
						'prop': 'kow_wph',
						'units': "log",
						'description': "pH-dependent octanol/water partition coefficient"
					}
				]
			}
		}


class Measured_CTS_REST(CTS_REST):
	"""
	CTS REST endpoints, etc. for EPI Suite
	"""
	def __init__(self):
		self.meta_info = {
			'metaInfo': {
				'model': "measured",
				'collection': "qed",
				'modelVersion': "EPI Suite 4.11",
				'description': "Measured data from EPI Suite 4.11.",
				'status': '',
				'timestamp': gen_jid(),
				'url': {
					'type': "application/json",
					'href': "http://qedinternal.epa.gov/cts/rest/measured"
				},
				'availableProps': [
					{
						'prop': 'melting_point',
						'units': 'degC',
						'description': "melting point",
						'method': "FDAMethod"
					},
					{
						'prop': 'boiling_point',
						'units': 'degC',
						'description': "boiling point"
					},
					{
						'prop': 'water_sol',
						'units': 'mg/L',
						'description': "water solubility"
					},
					{
						'prop': 'vapor_press',
						'units': 'mmHg',
						'description': "vapor pressure"
					},
					{
						'prop': 'henrys_law_con',
						'units': '(atm*m^3)/mol',
						'description': "henry's law constant"
					},
					{
						'prop': 'kow_no_ph',
						'units': "log",
						'description': "octanol/water partition coefficient"
					},
					{
						'prop': 'koc',
						'units': "L/kg",
						'description': "organic carbon partition coefficient"
					}
				]
			}
		}


class Metabolizer_CTS_REST(CTS_REST):
	"""
	CTS REST endpoints, etc. for EPI Suite
	"""
	def __init__(self):
		self.meta_info = {
			'metaInfo': {
				'model': "metabolizer",
				'collection': "qed",
				'modelVersion': "",
				'description': "",
				'status': '',
				'timestamp': gen_jid(),
				'url': {
					'type': "application/json",
					'href': "http://qedinternal.epa.gov/cts/rest/metabolizer"
				},

			}
		}
		self.inputs = {
			'structure': '',
			'generationLimit': 1,
			'transformationLibraries': ["hydrolysis", "abiotic_reduction", "human_biotransformation"]
		}


def showSwaggerPage(request):
	"""
	display swagger.json with swagger UI
	for CTS API docs/endpoints
	"""
	return render_to_response('cts_api/swagger_index.html')


def getChemicalEditorData(request):
	"""
	Makes call to Calculator for chemaxon
	data. Converts incoming structure to smiles,
	then filters smiles, and then retrieves data
	:param request:
	:return: chemical details response json

	Note: Due to marvin sketch image data (<cml> image) being
	so large, a bool, "structureData", is used to determine
	whether or not to grab it. It's only needed in chem edit tab.
	"""
	try:

		if 'message' in request.POST:
			# receiving request from cts_stress node server..
			# todo: should generalize and not have conditional
			request_post = json.loads(request.POST.get('message'))
		else:
			request_post = request.POST


		# chemical = request.POST.get('chemical')
		chemical = request_post.get('chemical')
		get_sd = request_post.get('get_structure_data')  # bool for getting <cml> format image for marvin sketch
		is_node = request_post.get('is_node')  # bool for tree node or not


		# Updated cheminfo workflow with actorws:
		###########################################################################################
		# 1. Determine if user's chemical is smiles, cas, or drawn
		# 		a. If smiles, get gsid from actorws chemicalIdentifier endpoint
		#		b. If cas, get chem data from actorws dsstox endpoint
		#		c. If drawn, get smiles from chemaxon, then gsid like in a.
		# 2. Check if request from 1. "matched" (exist?)
		#		a. If 1b returns cas result, get cheminfo from dsstox results
		#		b. If 1a or 1c, use gsid from chemicalIdentifier and perform step 1b for dsstox cheminfo
		# 3. Use dsstox results: curated CAS#, SMILES, preferredName, iupac, and dtxsid
		#		a. Display in chemical editor.
		#############################################################################################


		actorws = smilesfilter.ACTORWS()  # start w/ actorws instance from smilesfilter module
		calc = Calculator()  # calculator class instance

		# 1. Determine chemical type from user (e.g., smiles, cas, name, etc.):
		chem_type = Calculator().getChemicalType(chemical)

		logging.info("chem type: {}".format(chem_type))

		_gsid = None
		_jchem_smiles = None
		_name_or_smiles = chem_type['type'] == 'name' or chem_type['type'] == 'smiles'
		_actor_results = {}  # final key:vals from actorws: smiles, iupac, preferredName, dsstoxSubstanceId, casrn

		# Checking type for next step:
		if chem_type['type'] == 'mrv':
			logging.info("Getting SMILES from jchem web services..")
			response = calc.convertToSMILES({'chemical': chemical})
			_jchem_smiles = response['structure']
			logging.info("SMILES of drawn chemical: {}".format(_jchem_smiles))

		if _name_or_smiles or _jchem_smiles:
			logging.info("Getting gsid from actorws chemicalIdentifier..")
			chemid_results = actorws.get_chemid_results(chemical)  # obj w/ keys calc, prop, data
			_gsid = chemid_results['data']['gsid']
			logging.info("gsid from actorws chemid: {}".format(_gsid))
			_actor_results['gsid'] = _gsid

			# I think this is where a check needs to be for whether obtaining
			# gsid was successful. If not, get chem info from chemaxon like usual


		# Should be CAS# or have gsid from chemid by this point..
		if _gsid or chem_type['type'] == 'CAS#':
			id_type = 'CAS#'
			if _gsid:
				chem_id = _gsid
				id_type = 'gsid'
			logging.info("Getting results from actorws dsstox..")
			dsstox_results = actorws.get_dsstox_results(chem_id, id_type)  # keys: smiles, iupac, preferredName, dsstoxSubstanceId, casrn 
			_actor_results.update(dsstox_results)

			# TODO: The "matching?" part again. Just check if results were successful??

		# ?: Are the iupac, smiles, casrn used from actorws if available, and
		# if they're not then using just the values from chemaxon?
		# Also, are the additional cells in Chemical Editor that are for actorws
		# values going to be "N/A" if using chemaxon for chem info?

		# Need to figure out orig_smiles for smiles filter:
		# If user enters something other than SMILES, use actorws smiles for orig_smiles
		orig_smiles = ""
		if chem_type['type'] == 'smiles':
			orig_smiles = chemical  # use user-entered smiles as orig_siles
		elif 'smiles' in _actor_results:
			orig_smiles = _actor_results['smiles']  # use actorws smiles as orig_smiles
		else:
			logging.info("smiles not in user request or actorws results, getting from jchem ws..")
			orig_smiles = calc.convertToSMILES({'chemical': chemical}).get('structure')

		# response = Calculator().convertToSMILES({'chemical': chemical})
		# orig_smiles = response['structure']

		logging.info("original smiles before cts filtering: {}".format(orig_smiles))

		filtered_smiles_response = smilesfilter.filterSMILES(orig_smiles)
		filtered_smiles = filtered_smiles_response['results'][-1]

		logging.warning("Filtered SMILES: {}".format(filtered_smiles))

		jchem_response = Calculator().getChemDetails({'chemical': filtered_smiles})  # get chemical details

		molecule_obj = Molecule().createMolecule(chemical, orig_smiles, jchem_response, get_sd)

		# Loop _actor_results, replace certain keys in molecule_obj with actorws vals:
		for key, val in _actor_results['data'].items():
			# if key in molecule_obj:
			if key == 'casrn':
				molecule_obj['cas'] = val
			else:
				molecule_obj[key] = val  # replace or add any values from chemaxon deat
			# elif key in ['preferredName', 'dsstoxSubstanceId', 'casrn']:
			# 	molecule_obj[key] = val

		if is_node:
			molecule_obj.update({'node_image': Calculator().nodeWrapper(filtered_smiles, MetabolizerCalc().tree_image_height, MetabolizerCalc().tree_image_width, MetabolizerCalc().image_scale, MetabolizerCalc().metID,'svg', True)})
			molecule_obj.update({
				'popup_image': Calculator().popupBuilder(
					{"smiles": filtered_smiles}, 
					MetabolizerCalc().metabolite_keys, 
					"{}".format(request_post.get('id')),
					"Metabolite Information")
			})

		wrapped_post = {
			'status': True,  # 'metadata': '',
			'data': molecule_obj,
			'request_post': request_post
		}
		json_data = json.dumps(wrapped_post)

		logging.warning("Returning Chemical Info: {}".format(json_data))

		return HttpResponse(json_data, content_type='application/json')

	except KeyError as error:
		logging.warning(error)
		wrapped_post = {
			'status': False, 
			'error': 'Error validating chemical',
			'chemical': chemical
		}
		return HttpResponse(json.dumps(wrapped_post), content_type='application/json')
	except Exception as error:
		logging.warning(error)
		wrapped_post = {'status': False, 'error': error}
		return HttpResponse(json.dumps(wrapped_post), content_type='application/json')


# class Metabolite(Molecule):


def getChemicalSpeciationData(request_dict):
	"""
	CTS web service endpoint for getting
	chemical speciation data through  the
	chemspec model/class
	:param request - chemspec_model
	:return: chemical speciation data response json
	"""

	try:

		logging.info("Incoming request for speciation data: {}".format(request_dict))

		filtered_smiles_response = smilesfilter.filterSMILES(request_dict.get('chemical'))
		filtered_smiles = filtered_smiles_response['results'][-1]
		logging.info("Speciation filtered SMILES: {}".format(filtered_smiles))
		request_dict['chemical'] = filtered_smiles

		django_request = HttpResponse()
		django_request.POST = request_dict
		django_request.method = 'POST'

		chemspec_obj = chemspec_output.chemspecOutputPage(django_request)

		wrapped_post = {
			'status': True,  # 'metadata': '',
			'data': chemspec_obj.run_data
		}
		json_data = json.dumps(wrapped_post)

		logging.info("chemspec model data: {}".format(chemspec_obj))

		return HttpResponse(json_data, content_type='application/json')

	except Exception as error:
		logging.warning("Error in cts_rest, getChemicalSpecation(): {}".format(error))
		return HttpResponse("Error getting speciation data")


def gen_jid():
	ts = datetime.datetime.now(pytz.UTC)
	localDatetime = ts.astimezone(pytz.timezone('US/Eastern'))
	jid = localDatetime.strftime('%Y%m%d%H%M%S%f')
	return jid