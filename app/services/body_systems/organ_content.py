"""Educational organ page content catalog (Phase 4).

Content is for learning only — never a clinical diagnosis.
Keys align with Organ.content_json + learning_objectives / animation_key.
"""

from __future__ import annotations

from typing import Any

CONTENT_VERSION = "phase4-v1"


def _base_safety() -> dict[str, Any]:
  return {
    "educational_only": True,
    "not_a_diagnosis": True,
    "note": "For educational purposes only. Not a diagnosis or treatment plan.",
  }


def _pack(
  *,
  overview: str,
  location_detail: str,
  functions: list[str],
  parts: list[str],
  blood_supply: str,
  nerves: str,
  physiology: str,
  anatomy: str,
  clinical_importance: str,
  normal_anatomy: str,
  common_diseases: list[dict[str, str]],
  signs: list[str],
  symptoms: list[str],
  investigations: list[str],
  treatment_overview: str,
  nursing_care: list[str],
  complications: list[str],
  patient_education: list[str],
  prevention: list[str],
  clinical_pearls: list[str],
  animation_notes: str,
  learning_objectives: list[str],
  animation_key: str,
  short_description: str,
) -> dict[str, Any]:
  return {
    "short_description": short_description,
    "overview": overview,
    "animation_key": animation_key,
    "learning_objectives": learning_objectives,
    "content_json": {
      "version": CONTENT_VERSION,
      "overview": overview,
      "location_detail": location_detail,
      "functions": functions,
      "parts": parts,
      "blood_supply": blood_supply,
      "nerves": nerves,
      "physiology": physiology,
      "anatomy": anatomy,
      "clinical_importance": clinical_importance,
      "normal_anatomy": normal_anatomy,
      "common_diseases": common_diseases,
      "signs": signs,
      "symptoms": symptoms,
      "investigations": investigations,
      "treatment_overview": treatment_overview,
      "nursing_care": nursing_care,
      "complications": complications,
      "patient_education": patient_education,
      "prevention": prevention,
      "clinical_pearls": clinical_pearls,
      "images": [],
      "illustrations": [],
      "animation_notes": animation_notes,
      "safety": _base_safety(),
    },
  }


ORGAN_CONTENT: dict[str, dict[str, Any]] = {
  "heart": _pack(
    short_description="Muscular pump that drives pulmonary and systemic circulation.",
    overview=(
      "The heart is a four-chambered muscular organ that continuously pumps blood "
      "through the pulmonary and systemic circuits. Understanding its chambers, valves, "
      "conduction system, and coronary circulation is foundational for cardiovascular nursing "
      "and medicine education."
    ),
    location_detail="Mediastinum in the thorax, slightly left of midline behind the sternum.",
    functions=[
      "Pump deoxygenated blood to the lungs (right heart)",
      "Pump oxygenated blood to the body (left heart)",
      "Maintain cardiac output matched to metabolic demand",
      "Generate electrical impulses for coordinated contraction",
    ],
    parts=[
      "Right atrium and right ventricle",
      "Left atrium and left ventricle",
      "Tricuspid, pulmonary, mitral, and aortic valves",
      "Septa (interatrial and interventricular)",
      "Pericardium, myocardium, endocardium",
      "Sinoatrial (SA) and atrioventricular (AV) nodes",
    ],
    blood_supply=(
      "Coronary arteries (left and right) arise from the aortic root and supply the myocardium. "
      "Venous return occurs mainly via the coronary sinus into the right atrium."
    ),
    nerves=(
      "Autonomic innervation: sympathetic fibers increase rate and contractility; "
      "parasympathetic (vagus) fibers decrease rate. Sensory afferents travel with autonomic nerves."
    ),
    physiology=(
      "Cardiac cycle: diastole (filling) and systole (ejection). Stroke volume × heart rate = "
      "cardiac output. Frank–Starling relationship links preload to stroke volume within physiologic limits."
    ),
    anatomy=(
      "Apex points leftward and inferiorly; base is superior. The left ventricle has thicker walls "
      "to generate systemic pressure. Valves ensure unidirectional flow."
    ),
    clinical_importance=(
      "Heart pathology underlies common presentations such as chest pain, dyspnea, edema, and "
      "arrhythmias. Learners should map anatomy to ECG leads, heart sounds, and imaging views."
    ),
    normal_anatomy=(
      "Healthy adult resting heart rate typically ~60–100 bpm; S1/S2 heart sounds correspond to "
      "AV and semilunar valve closure. Chambers and valves appear structurally intact on imaging."
    ),
    common_diseases=[
      {"name": "Coronary artery disease (educational)", "summary": "Atherosclerotic narrowing of coronary arteries."},
      {"name": "Heart failure (educational)", "summary": "Impaired ability to meet metabolic demand."},
      {"name": "Arrhythmias (educational)", "summary": "Abnormal rate or rhythm from conduction issues."},
      {"name": "Valvular heart disease (educational)", "summary": "Stenosis or regurgitation of one or more valves."},
    ],
    signs=["Abnormal heart sounds", "Peripheral edema", "Jugular venous distension (when present)", "Cyanosis (severe cases)"],
    symptoms=["Chest discomfort", "Shortness of breath", "Palpitations", "Fatigue", "Syncope (selected cases)"],
    investigations=["ECG", "Chest X-ray", "Echocardiography", "Cardiac biomarkers (context-dependent)", "Stress testing / angiography (advanced)"],
    treatment_overview=(
      "Educational overview only: lifestyle measures, medications (e.g. antiplatelets, antihypertensives, "
      "rate/rhythm agents), reperfusion strategies, and device/surgical options depending on condition — "
      "always guided by licensed clinicians."
    ),
    nursing_care=[
      "Monitor vital signs, SpO2, and fluid balance",
      "Assess pain, dyspnea, and activity tolerance",
      "Support medication adherence education",
      "Recognize red-flag symptoms for escalation",
    ],
    complications=["Cardiogenic shock", "Thromboembolism", "Pulmonary edema", "Sudden cardiac arrest"],
    patient_education=[
      "Medication and follow-up importance",
      "Sodium and fluid guidance when prescribed",
      "When to seek urgent care for chest pain or severe dyspnea",
    ],
    prevention=["Blood pressure and lipid control education", "Smoking cessation", "Physical activity as advised", "Diabetes management education"],
    clinical_pearls=[
      "Left ventricular failure often presents with pulmonary symptoms; right-sided failure with systemic congestion.",
      "Heart sounds and ECG together help localize educational differentials.",
    ],
    animation_notes="Heart pumping animation illustrates systole/diastole rhythm for learning.",
    learning_objectives=[
      "Identify the four chambers and four valves",
      "Explain pulmonary vs systemic circuits",
      "Relate coronary supply to ischemic presentations (educational)",
      "Describe basic nursing assessments for cardiac patients",
    ],
    animation_key="heart_pumping",
  ),
  "lungs": _pack(
    short_description="Paired organs for gas exchange between air and blood.",
    overview=(
      "The lungs enable oxygen uptake and carbon dioxide elimination. Learners should connect "
      "airway anatomy, alveolar–capillary gas exchange, and ventilation–perfusion concepts."
    ),
    location_detail="Thoracic cavity, flanking the mediastinum within the pleural sacs.",
    functions=["Gas exchange (O2/CO2)", "Acid–base contribution via CO2 elimination", "Filter small emboli (physiologic)", "Speech support via airflow"],
    parts=["Trachea and bronchi", "Bronchioles", "Alveoli", "Pleura (visceral/parietal)", "Pulmonary vasculature", "Lobes (right 3 / left 2)"],
    blood_supply="Pulmonary arteries carry deoxygenated blood; pulmonary veins return oxygenated blood. Bronchial arteries supply airway tissue.",
    nerves="Pulmonary plexus (sympathetic and parasympathetic) regulates airway tone and secretions; stretch receptors influence breathing patterns.",
    physiology="Ventilation moves air; diffusion occurs across the blood–gas barrier; perfusion delivers blood. Matching V/Q is critical for efficient exchange.",
    anatomy="Right lung: superior, middle, inferior lobes. Left lung: superior and inferior lobes with cardiac notch.",
    clinical_importance="Respiratory symptoms are among the most common learning cases — link anatomy to auscultation zones and imaging patterns.",
    normal_anatomy="Clear lung fields on educational imaging examples; vesicular breath sounds; SpO2 typically high in healthy individuals at sea level.",
    common_diseases=[
      {"name": "Pneumonia (educational)", "summary": "Infection of lung parenchyma."},
      {"name": "Asthma (educational)", "summary": "Reversible airway obstruction and inflammation."},
      {"name": "COPD (educational)", "summary": "Chronic airflow limitation."},
      {"name": "Pulmonary embolism (educational)", "summary": "Obstruction of pulmonary arterial flow."},
    ],
    signs=["Abnormal breath sounds", "Tachypnea", "Use of accessory muscles", "Cyanosis (severe)"],
    symptoms=["Dyspnea", "Cough", "Wheeze", "Chest tightness", "Hemoptysis (selected)"],
    investigations=["Pulse oximetry", "ABG (context)", "Chest X-ray", "CT / CTPA (advanced)", "Spirometry"],
    treatment_overview="Educational only: oxygen therapy principles, bronchodilators, anti-infectives, physiotherapy, and escalation pathways per clinical protocols.",
    nursing_care=["Airway and breathing assessment", "Positioning for ventilation", "Oxygen safety education", "Suctioning / secretion support as ordered"],
    complications=["Respiratory failure", "Pneumothorax", "Cor pulmonale", "Hypoxemic organ injury"],
    patient_education=["Inhaler technique", "Smoking cessation", "When to escalate for worsening dyspnea"],
    prevention=["Vaccination education where relevant", "Infection control", "Occupational exposure awareness"],
    clinical_pearls=["Auscultate systematically by zones.", "Hypoxia and hypercapnia have different educational red flags."],
    animation_notes="Respiration animation shows inspiration/expiration volume change.",
    learning_objectives=[
      "Describe airway generations to alveoli",
      "Explain gas exchange at the alveolar–capillary membrane",
      "Map common findings to educational differentials",
    ],
    animation_key="respiration",
  ),
  "brain": _pack(
    short_description="Central organ of the nervous system controlling cognition, sensation, and motor function.",
    overview="The brain integrates sensory input, coordinates motor output, and supports cognition, emotion, and autonomic control.",
    location_detail="Cranial cavity, protected by skull, meninges, and cerebrospinal fluid.",
    functions=["Cognition and memory", "Motor control", "Sensory processing", "Autonomic regulation", "Language and emotion"],
    parts=["Cerebrum", "Cerebellum", "Brainstem", "Diencephalon", "Meninges", "Ventricular system"],
    blood_supply="Circle of Willis connects internal carotid and vertebrobasilar systems; venous drainage via dural sinuses.",
    nerves="Cranial nerves I–XII emerge from brain/brainstem; central pathways form ascending and descending tracts.",
    physiology="Neurons communicate via action potentials and synapses. Cerebral blood flow autoregulation protects perfusion across a range of pressures.",
    anatomy="Gray matter (cortex/nuclei) and white matter tracts; lobes: frontal, parietal, temporal, occipital.",
    clinical_importance="Stroke, seizure, and raised ICP presentations require rapid recognition frameworks for learners.",
    normal_anatomy="Symmetric hemispheres, patent ventricles, preserved gray–white differentiation on educational imaging examples.",
    common_diseases=[
      {"name": "Ischemic stroke (educational)", "summary": "Focal brain ischemia from vascular occlusion."},
      {"name": "Intracerebral hemorrhage (educational)", "summary": "Bleeding within brain parenchyma."},
      {"name": "Seizure disorders (educational)", "summary": "Abnormal synchronized neuronal firing."},
      {"name": "Meningitis (educational)", "summary": "Inflammation of the meninges."},
    ],
    signs=["Focal neurologic deficits", "Altered consciousness", "Abnormal reflexes", "Meningism (selected)"],
    symptoms=["Headache", "Weakness", "Speech difficulty", "Visual changes", "Confusion"],
    investigations=["Neurologic exam", "CT / MRI", "EEG", "Lumbar puncture (selected)", "Labs as indicated"],
    treatment_overview="Educational only: time-critical pathways (e.g. stroke), anticonvulsants, antimicrobials, ICP care principles — clinician-directed.",
    nursing_care=["GCS / neuro observations", "Airway protection", "Seizure precautions", "ICP precaution education"],
    complications=["Raised ICP", "Herniation syndromes", "Aspiration", "Permanent deficit"],
    patient_education=["Stroke FAST education", "Medication adherence", "Safety after neurologic events"],
    prevention=["BP control education", "Anticoagulation adherence when prescribed", "Helmet / injury prevention"],
    clinical_pearls=["Localize lesion by deficit pattern.", "Time is brain in stroke education frameworks."],
    animation_notes="Neuron signal animation illustrates impulse propagation conceptually.",
    learning_objectives=["Name major brain regions", "Explain Circle of Willis significance", "Recognize educational stroke warning signs"],
    animation_key="neuron_signal",
  ),
  "kidneys": _pack(
    short_description="Paired retroperitoneal organs that filter blood and regulate fluid, electrolytes, and acid–base balance.",
    overview="Kidneys maintain homeostasis through filtration, reabsorption, secretion, and hormone production (e.g. erythropoietin, renin).",
    location_detail="Retroperitoneal, flank regions roughly at T12–L3; right kidney slightly lower.",
    functions=["Filter blood / form urine", "Regulate volume and electrolytes", "Acid–base balance", "BP via renin–angiotensin", "RBC production support (EPO)"],
    parts=["Cortex", "Medulla / pyramids", "Nephrons", "Pelvis", "Ureters (drainage)", "Renal vessels"],
    blood_supply="Renal arteries from aorta; high blood flow relative to size. Venous return via renal veins to IVC.",
    nerves="Renal plexus (sympathetic predominant) influences vascular tone and renin release.",
    physiology="Glomerular filtration → tubular processing → collecting system. GFR is a key educational metric of kidney function.",
    anatomy="Bean-shaped; hilum transmits vessels, nerves, and ureter. Capsule and fascia provide support.",
    clinical_importance="AKI, CKD, and electrolyte disorders are high-yield for nursing and medical learners.",
    normal_anatomy="Symmetric size, smooth contours, patent collecting systems on educational imaging examples.",
    common_diseases=[
      {"name": "Acute kidney injury (educational)", "summary": "Sudden decline in kidney function."},
      {"name": "Chronic kidney disease (educational)", "summary": "Progressive loss of kidney function."},
      {"name": "Pyelonephritis (educational)", "summary": "Infection involving the kidney."},
      {"name": "Nephrolithiasis (educational)", "summary": "Kidney stone disease."},
    ],
    signs=["Oliguria / anuria", "Edema", "Hypertension", "Costovertebral angle tenderness"],
    symptoms=["Flank pain", "Dysuria (associated UTI)", "Fatigue", "Nausea"],
    investigations=["Creatinine / eGFR", "Electrolytes", "Urinalysis", "Ultrasound", "ABG (selected)"],
    treatment_overview="Educational only: fluid/electrolyte strategies, infection treatment, dialysis concepts, stone pathways — clinician-directed.",
    nursing_care=["Strict intake/output", "Daily weights", "Nephrotoxin awareness education", "Access care for dialysis learners"],
    complications=["Hyperkalemia", "Fluid overload", "Uremia", "Infection"],
    patient_education=["Medication review with clinician", "Diet/fluid guidance when prescribed", "Infection symptom reporting"],
    prevention=["Hydration education", "BP/diabetes control education", "Avoid unnecessary nephrotoxins"],
    clinical_pearls=["Pre-renal vs intrinsic vs post-renal is a core educational framework.", "Trends in creatinine matter as much as single values."],
    animation_notes="Filtration animation shows nephron-level flow conceptually.",
    learning_objectives=["Describe nephron function", "Explain GFR conceptually", "List high-yield electrolyte risks"],
    animation_key="kidney_filtration",
  ),
  "liver": _pack(
    short_description="Largest internal organ; central to metabolism, detoxification, and synthesis.",
    overview="The liver processes nutrients, synthesizes proteins (including clotting factors), metabolizes drugs, and produces bile.",
    location_detail="Right upper quadrant of the abdomen, beneath the diaphragm.",
    functions=["Metabolism of carbs/lipids/proteins", "Bile production", "Detoxification / drug metabolism", "Synthesis of albumin and clotting factors", "Storage (glycogen, vitamins)"],
    parts=["Right and left lobes", "Caudate and quadrate lobes", "Portal triad", "Hepatic lobules", "Biliary tree connections"],
    blood_supply="Dual supply: hepatic artery (oxygenated) and portal vein (nutrient-rich). Hepatic veins drain to IVC.",
    nerves="Hepatic plexus; autonomic fibers influence vascular tone and biliary function.",
    physiology="Hepatocytes perform metabolism and synthesis; Kupffer cells contribute to immune filtering of portal blood.",
    anatomy="Covered by Glisson’s capsule; falciform ligament divides anatomic lobes.",
    clinical_importance="Jaundice, coagulopathy, and portal hypertension concepts are core learning themes.",
    normal_anatomy="Homogeneous parenchyma, smooth contour, patent portal flow on educational ultrasound examples.",
    common_diseases=[
      {"name": "Hepatitis (educational)", "summary": "Inflammation of the liver."},
      {"name": "Cirrhosis (educational)", "summary": "Chronic fibrosis with architectural distortion."},
      {"name": "Fatty liver disease (educational)", "summary": "Hepatic steatosis spectrum."},
      {"name": "Cholelithiasis-related issues (educational)", "summary": "Gallstone-related biliary obstruction themes."},
    ],
    signs=["Jaundice", "Ascites", "Spider angiomas", "Hepatomegaly / shrunken liver (varies)"],
    symptoms=["Fatigue", "RUQ discomfort", "Pruritus", "Easy bruising", "Confusion (advanced)"],
    investigations=["LFTs", "Coagulation panel", "Viral serologies", "Ultrasound", "Elastography / biopsy (advanced)"],
    treatment_overview="Educational only: treat underlying cause, support nutrition, manage complications — clinician-directed.",
    nursing_care=["Monitor mental status", "Skin care for jaundice/pruritus", "Bleeding precautions education", "Ascites comfort measures"],
    complications=["Portal hypertension", "Variceal bleeding", "Hepatic encephalopathy", "Coagulopathy"],
    patient_education=["Alcohol risk education", "Medication hepatotoxicity awareness", "Vaccination where relevant"],
    prevention=["Vaccination education", "Safe prescribing awareness", "Metabolic risk reduction"],
    clinical_pearls=["Synthetic function (INR, albumin) often matters more educationally than isolated enzyme spikes.", "Portal HTN explains many exam findings."],
    animation_notes="Digestion/metabolism animation highlights hepatic processing role.",
    learning_objectives=["Explain dual blood supply", "List key synthetic functions", "Relate jaundice to bilirubin pathways (educational)"],
    animation_key="digestion",
  ),
  "stomach": _pack(
    short_description="Muscular reservoir that initiates protein digestion and regulates gastric emptying.",
    overview="The stomach stores ingested food, mixes it into chyme, and begins protein digestion via acid and pepsin.",
    location_detail="Left upper quadrant, epigastric region, between esophagus and duodenum.",
    functions=["Mechanical mixing", "Acid secretion", "Pepsinogen → pepsin activation", "Intrinsic factor production", "Controlled emptying to duodenum"],
    parts=["Cardia", "Fundus", "Body", "Antrum", "Pylorus", "Rugae", "Sphincters (LES / pyloric)"],
    blood_supply="Branches of the celiac trunk (left/right gastric, gastroepiploic, short gastrics).",
    nerves="Vagus (parasympathetic) stimulates secretion/motility; sympathetic fibers via celiac plexus inhibit.",
    physiology="Gastric phases (cephalic, gastric, intestinal) regulate acid and motility. Mucosal barrier protects against autodigestion.",
    anatomy="J-shaped hollow organ with greater and lesser curvatures; three muscle layers enable churning.",
    clinical_importance="Ulcer disease, bleeding, and obstruction themes are high-yield for GI education.",
    normal_anatomy="Intact mucosa, patent pylorus, appropriate emptying on educational studies.",
    common_diseases=[
      {"name": "Peptic ulcer disease (educational)", "summary": "Ulceration of gastric or duodenal mucosa."},
      {"name": "Gastritis (educational)", "summary": "Inflammation of gastric mucosa."},
      {"name": "GERD-related themes (educational)", "summary": "Reflux of gastric contents."},
      {"name": "Gastric outlet obstruction (educational)", "summary": "Impaired emptying through the pylorus."},
    ],
    signs=["Epigastric tenderness", "Melena / hematemesis (bleeding)", "Succussion splash (selected)"],
    symptoms=["Epigastric pain", "Nausea", "Early satiety", "Heartburn", "Vomiting"],
    investigations=["H. pylori testing", "CBC", "Upper endoscopy", "Urea breath test", "Imaging if obstruction suspected"],
    treatment_overview="Educational only: acid suppression, H. pylori regimens, bleeding pathways — clinician-directed.",
    nursing_care=["NPO when ordered", "Monitor for GI bleed signs", "Pain and antiemetic support", "Nutrition progression"],
    complications=["Bleeding", "Perforation", "Obstruction", "Anemia"],
    patient_education=["NSAID risk awareness", "Alarm symptom recognition", "Lifestyle measures for reflux education"],
    prevention=["Judicious NSAID use education", "H. pylori testing/treatment education", "Smoking cessation"],
    clinical_pearls=["Alarm features (weight loss, bleeding, anemia) change the educational urgency.", "Mucosal barrier failure is central to ulcer themes."],
    animation_notes="Digestion animation shows mixing and emptying conceptually.",
    learning_objectives=["Name stomach regions", "Explain acid–pepsin role", "List GI bleed warning signs for learners"],
    animation_key="digestion",
  ),
  "pancreas": _pack(
    short_description="Gland with exocrine digestive enzymes and endocrine islet hormones.",
    overview="The pancreas has dual roles: exocrine enzyme secretion into the duodenum and endocrine regulation of glucose via islet hormones.",
    location_detail="Retroperitoneal, transversely across the upper abdomen behind the stomach.",
    functions=["Secrete digestive enzymes", "Bicarbonate-rich fluid", "Insulin / glucagon / somatostatin", "Support nutrient absorption"],
    parts=["Head, neck, body, tail", "Main and accessory ducts", "Acini", "Islets of Langerhans"],
    blood_supply="Branches from celiac and superior mesenteric arteries; venous drainage ultimately to portal system.",
    nerves="Autonomic plexus; rich visceral afferents explain severe pain in pancreatitis education.",
    physiology="Exocrine secretion timed with meals; endocrine islets respond to glucose and other signals to maintain glycemia.",
    anatomy="Head nestles in duodenal C-loop; tail extends toward the spleen.",
    clinical_importance="Pancreatitis and diabetes educational pathways are clinically high-yield.",
    normal_anatomy="Homogeneous parenchyma, non-dilated duct on educational imaging examples.",
    common_diseases=[
      {"name": "Acute pancreatitis (educational)", "summary": "Acute inflammation of the pancreas."},
      {"name": "Chronic pancreatitis (educational)", "summary": "Long-standing inflammation with fibrosis."},
      {"name": "Diabetes mellitus themes (educational)", "summary": "Impaired insulin production or action."},
      {"name": "Pancreatic cancer (educational overview)", "summary": "Malignancy often presenting late — learning recognition only."},
    ],
    signs=["Epigastric tenderness", "Ileus (selected)", "Cullen/Grey Turner (rare educational signs)"],
    symptoms=["Severe epigastric pain radiating to back", "Nausea/vomiting", "Anorexia", "Steatorrhea (chronic)"],
    investigations=["Lipase / amylase", "Glucose", "Ultrasound / CT", "MRCP (selected)", "HbA1c (endocrine context)"],
    treatment_overview="Educational only: supportive care in pancreatitis, enzyme replacement, glycemic therapies — clinician-directed.",
    nursing_care=["Pain assessment", "Fluid status monitoring", "Glucose checks when ordered", "Nutrition support awareness"],
    complications=["Necrosis / infection", "Pseudocyst", "Organ failure", "Malabsorption"],
    patient_education=["Alcohol risk education", "Diabetes sick-day basics (when taught)", "Enzyme timing with meals if prescribed"],
    prevention=["Alcohol moderation education", "Gallstone awareness", "Metabolic health education"],
    clinical_pearls=["Pain pattern to the back is a classic educational clue.", "Exocrine vs endocrine failure present differently."],
    animation_notes="Digestion animation highlights enzyme release into the duodenum.",
    learning_objectives=["Distinguish exocrine vs endocrine roles", "List pancreatitis learning red flags", "Explain insulin’s educational role in glucose control"],
    animation_key="digestion",
  ),
  "spleen": _pack(
    short_description="Lymphoid organ that filters blood and supports immune responses.",
    overview="The spleen filters blood, recycles red cell components, and contributes to immune surveillance, especially against encapsulated organisms.",
    location_detail="Left upper quadrant, beneath the diaphragm, protected by lower ribs.",
    functions=["Blood filtration", "Immune response support", "Platelet / cell reservoir", "Remove abnormal RBCs"],
    parts=["White pulp", "Red pulp", "Capsule and trabeculae", "Hilum with vessels"],
    blood_supply="Splenic artery (celiac trunk branch); splenic vein joins SMV to form portal vein.",
    nerves="Autonomic fibers via celiac plexus; visceral pain referral patterns are educationally relevant in trauma.",
    physiology="Blood percolates through pulp; immune cells interact with antigens in white pulp.",
    anatomy="Soft, friable organ; size varies with age and physiologic state.",
    clinical_importance="Trauma, splenomegaly, and post-splenectomy infection risk are key learning themes.",
    normal_anatomy="Homogeneous parenchyma within expected size range on educational imaging.",
    common_diseases=[
      {"name": "Splenic trauma (educational)", "summary": "Injury risk due to friable structure."},
      {"name": "Splenomegaly (educational)", "summary": "Enlargement from multiple systemic causes."},
      {"name": "Infarction (educational)", "summary": "Ischemic injury of splenic tissue."},
      {"name": "Post-splenectomy infection risk (educational)", "summary": "Increased risk from encapsulated bacteria."},
    ],
    signs=["LUQ tenderness", "Kehr’s sign (referred pain themes)", "Splenomegaly on exam (selected)"],
    symptoms=["LUQ pain", "Fullness", "Symptoms of underlying systemic disease"],
    investigations=["CBC", "Ultrasound / CT", "Peripheral smear (context)", "Infectious workup as indicated"],
    treatment_overview="Educational only: trauma pathways, vaccination strategies post-splenectomy, treat underlying cause — clinician-directed.",
    nursing_care=["Trauma ABCs", "Serial abdominal assessments", "Vaccination education after splenectomy", "Infection vigilance education"],
    complications=["Hemorrhage", "Overwhelming post-splenectomy infection", "Portal hypertension associations"],
    patient_education=["Seek care for fever after splenectomy", "Vaccination schedule importance", "Travel/infection precautions education"],
    prevention=["Seatbelt / trauma prevention", "Vaccination when indicated"],
    clinical_pearls=["Spleen is highly vascular — trauma is time-critical educationally.", "Encapsulated organisms matter after splenectomy."],
    animation_notes="Immune filtering concept animation (lightweight pulse).",
    learning_objectives=["Explain red vs white pulp roles", "List post-splenectomy learning risks", "Locate spleen anatomically"],
    animation_key="immune_pulse",
  ),
  "bones": _pack(
    short_description="Rigid organs forming the skeleton for support, protection, and mineral homeostasis.",
    overview="Bones provide structural support, protect organs, enable movement with muscles, house marrow, and store minerals.",
    location_detail="Whole body — axial and appendicular skeleton.",
    functions=["Support and protection", "Levers for movement", "Hematopoiesis in marrow", "Calcium/phosphate reservoir"],
    parts=["Compact bone", "Cancellous bone", "Periosteum", "Marrow cavity", "Epiphysis / metaphysis / diaphysis (long bones)"],
    blood_supply="Nutrient arteries, periosteal vessels, and metaphyseal/epiphyseal vessels; fracture healing depends on vascularity.",
    nerves="Periosteum is richly innervated — explains fracture pain intensity educationally.",
    physiology="Remodeling via osteoblasts/osteoclasts responds to load and systemic signals (PTH, vitamin D, etc.).",
    anatomy="206 bones in typical adult; classification: long, short, flat, irregular, sesamoid.",
    clinical_importance="Fractures, osteoporosis, and marrow disorders are high-yield across specialties.",
    normal_anatomy="Intact cortex/medulla relationships; age-appropriate density on educational radiographs.",
    common_diseases=[
      {"name": "Fractures (educational)", "summary": "Break in bone continuity."},
      {"name": "Osteoporosis (educational)", "summary": "Reduced bone mass and microarchitecture."},
      {"name": "Osteomyelitis (educational)", "summary": "Bone infection."},
      {"name": "Metastatic bone disease (educational overview)", "summary": "Secondary involvement of bone."},
    ],
    signs=["Deformity", "Point tenderness", "Crepitus (selected)", "Swelling"],
    symptoms=["Pain", "Loss of function", "Inability to bear weight"],
    investigations=["X-ray", "CT / MRI", "Bone density (DEXA)", "Labs (Ca, ALP, vitamin D as indicated)"],
    treatment_overview="Educational only: immobilization, reduction, fixation concepts, metabolic therapies — clinician-directed.",
    nursing_care=["Neurovascular checks", "Pain and cast care education", "DVT prophylaxis awareness", "Mobility support"],
    complications=["Compartment syndrome", "Fat embolism (selected)", "Nonunion", "Infection"],
    patient_education=["Fall prevention", "Cast warning signs", "Calcium/vitamin D education when advised"],
    prevention=["Fall risk reduction", "Weight-bearing exercise education", "Bone health screening awareness"],
    clinical_pearls=["Neurovascular status distal to injury is mandatory in fracture education.", "Osteoporosis is silent until fracture."],
    animation_notes="Subtle structural highlight animation for skeletal framework.",
    learning_objectives=["Classify bone types", "Explain remodeling cells", "List fracture nursing priorities"],
    animation_key="skeletal_frame",
  ),
  "muscles": _pack(
    short_description="Contractile tissue enabling movement, posture, and heat production.",
    overview="Skeletal muscle generates voluntary movement; smooth and cardiac muscle serve visceral and cardiac roles. This page focuses on skeletal muscle learning.",
    location_detail="Whole body — attached to bones via tendons across joints.",
    functions=["Produce movement", "Maintain posture", "Stabilize joints", "Generate heat"],
    parts=["Muscle belly", "Fascicles", "Fibers (myofibrils)", "Tendons", "Neuromuscular junction"],
    blood_supply="Regional arteries supply high metabolic demand during activity; venous return aided by muscle pump.",
    nerves="Somatic motor neurons via neuromuscular junctions; proprioceptors provide feedback.",
    physiology="Sliding filament theory: actin–myosin cross-bridges powered by ATP; motor units grade force.",
    anatomy="Origin vs insertion; agonist/antagonist/synergist relationships around joints.",
    clinical_importance="Weakness, myopathies, and injury patterns appear across neuro and MSK curricula.",
    normal_anatomy="Symmetric bulk and tone; full range of motion without pain in healthy examples.",
    common_diseases=[
      {"name": "Strain / tear (educational)", "summary": "Muscle fiber injury from overload."},
      {"name": "Myositis (educational)", "summary": "Inflammatory muscle disease themes."},
      {"name": "Neuromuscular junction disorders (educational)", "summary": "Impaired transmission (e.g. myasthenia themes)."},
      {"name": "Disuse atrophy (educational)", "summary": "Loss of bulk from inactivity."},
    ],
    signs=["Weakness", "Atrophy", "Swelling / bruising", "Reduced ROM"],
    symptoms=["Pain", "Cramping", "Fatigue with use", "Stiffness"],
    investigations=["CK (context)", "EMG / NCS", "MRI", "Strength testing scales"],
    treatment_overview="Educational only: RICE principles, physiotherapy, disease-specific therapies — clinician-directed.",
    nursing_care=["Functional assessment", "Pain and mobility plans", "DVT risk with immobility", "Rehab reinforcement"],
    complications=["Rhabdomyolysis (severe)", "Contractures", "Falls from weakness"],
    patient_education=["Gradual return to activity", "Ergonomics", "When severe pain/swelling needs review"],
    prevention=["Warm-up / conditioning education", "Workplace ergonomics", "Fall prevention with weakness"],
    clinical_pearls=["Motor unit recruitment explains graded strength.", "Distinguish neurologic vs primary muscle weakness educationally."],
    animation_notes="Contraction pulse animation for educational visualization.",
    learning_objectives=["Explain sliding filament concept", "Define origin/insertion", "List strain first-aid learning points"],
    animation_key="muscle_contraction",
  ),
}


def get_organ_content(slug: str) -> dict[str, Any] | None:
  return ORGAN_CONTENT.get((slug or "").strip().lower())


def needs_phase4_enrichment(organ) -> bool:
  """True when organ still has Phase-1 placeholder content."""
  cj = organ.content_json if isinstance(getattr(organ, "content_json", None), dict) else {}
  if cj.get("version") == CONTENT_VERSION:
    return False
  if cj.get("overview"):
    return False
  functions = cj.get("functions")
  if isinstance(functions, list) and any(functions):
    return False
  return True


def apply_organ_content(organ, pack: dict[str, Any]) -> None:
  organ.short_description = pack.get("short_description") or organ.short_description
  organ.overview = pack.get("overview") or organ.overview
  organ.animation_key = pack.get("animation_key") or organ.animation_key
  organ.learning_objectives = pack.get("learning_objectives") or organ.learning_objectives
  organ.content_json = pack.get("content_json") or organ.content_json
