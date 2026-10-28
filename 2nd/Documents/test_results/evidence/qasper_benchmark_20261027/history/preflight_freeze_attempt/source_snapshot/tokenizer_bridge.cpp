#include <llama.h>
#include <cstdint>
extern "C" {
void * tokenizer_open(const char * path) {
    llama_model_params p = llama_model_default_params();
    p.vocab_only = true;
    return llama_model_load_from_file(path, p);
}
int32_t tokenizer_count(void * model, const char * text, int32_t length) {
    const auto * vocab = llama_model_get_vocab(static_cast<llama_model *>(model));
    int32_t n = llama_tokenize(vocab, text, length, nullptr, 0, false, true);
    return n < 0 ? -n : n;
}
void tokenizer_close(void * model) { llama_model_free(static_cast<llama_model *>(model)); }
int32_t tokenizer_context(void * model) { return llama_model_n_ctx_train(static_cast<llama_model *>(model)); }
}
