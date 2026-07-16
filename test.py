import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
completion = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[
      {
        "role": "user",
        "content": "'messages': [{'role': 'system', 'content': '\\nYou validate a phone-number rule parser.\\n\\nEach cell contains:\\n- a template\\n- parser output\\n\\nValidate ONLY whether the parser output follows the grammar below.\\n\\n\\nGrammar\\n\\nVariables:\\nA-Z represent digit positions.\\n\\nOperators:\\n=  allowed values\\n#  not equal (displayed as ∉)\\n>, >=, <, <=\\n\\nRules:\\nA=1,2,B      -> A ∈ {1,2,B}\\nA#B          -> A ∉ {B}\\nA#5,B          -> A ∉ {5,B}\\nAB#12        -> A#1 OR B#2\\nAB=12        -> A=1 AND B=2\\n\\n# chains expand into ALL pairwise comparisons.\\n\\nExamples:\\nA#B#C\\n-> A#B\\n-> A#C\\n-> B#C\\n\\nA#B#5\\n-> A#B\\n-> A#5\\n-> B#5\\n\\nComma-separated conditions mean AND.\\n\\nExample:\\nA#B, A#1 and B#2\\nmeans\\nA#B AND A#1 AND B#2\\n\\nCheck each cell independently.\\n\\nReport issues only if one of these applies:\\n\\n1. incorrect_parse (severity: \"fail\")\\n   - The parsed output does not exactly match the grammar.\\n   - Missing, extra, or incorrect parsed conditions are failures.\\n   - Do not accept alternative interpretations.\\n\\n2. quirky_syntax (severity: \"warn\")\\n   Report only for potentially confusing input syntax, such as:\\n   - values outside 0-9 (e.g. A=12)\\n   - unusual template characters mixed with variables\\n   - malformed separators or spacing that could change parsing\\n\\n\\nReturn ONLY a JSON object.\\n\\nIssue format: {\"type\": \"incorrect_parse\"|\"quirky_syntax\", \"severity\": \"warn\"|\"fail\", \"detail\": \"...\"}\\n'}, {'role': 'user', 'content': 'Cells to validate:\\n\\n[0]\\n  Cell: 095A.B8A.BCD (A#B,C,D, B#C)\\n  Req: A#B,C,D, B#C\\n  \"parsed_conditions\":[\"A ∉ {B}\", \"C ∉ {C}\", \"D ∉ {C}\", \"B ∉ {C}\"]'}], 'temperature': 0}"
      },
      {
        "role": "assistant",
        "content": "{\n  \"issues\": [\n    {\n      \"type\": \"incorrect_parse\",\n      \"severity\": \"fail\",\n      \"detail\": \"The parsed_conditions do not correspond to the required rule \\\"A#B,C,D, B#C\\\". The rule expects conditions A#B, C, D, and B#C, but the parser output contains \\\"A ∉ {B}\\\", \\\"C ∉ {C}\\\", \\\"D ∉ {C}\\\", and \\\"B ∉ {C}\\\". It mis‑interprets the standalone variables C and D as \\\"C ∉ {C}\\\" and \\\"D ∉ {C}\\\", and it replaces the required \\\"B#C\\\" with \\\"B ∉ {C}\\\". This is a mismatch in both the set of conditions and their meanings.\"\n    },\n    {\n      \"type\": \"quirky_syntax\",\n      \"severity\": \"warn\",\n      \"detail\": \"The rule string contains standalone variables (\\\"C\\\" and \\\"D\\\") without an operator, which is non‑standard syntax and can lead to ambiguous parsing.\"\n    }\n  ]\n}"
      },
      {
        "role": "user",
        "content": ""
      }
    ],
    temperature=1,
    max_completion_tokens=8192,
    top_p=1,
    reasoning_effort="medium",
    stream=True,
    stop=None
)

for chunk in completion:
    print(chunk.choices[0].delta.content or "", end="")
